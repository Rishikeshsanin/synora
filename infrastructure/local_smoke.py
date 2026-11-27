"""Opt-in disposable CPU-only Docker Compose smoke. No cloud access or real generation.

Run with Python 3.12 in the existing hash-locked QA environment. No credentials are
written to disk; Docker daemon administrators can inspect disposable container env.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OWNER_A = "11111111-1111-4111-8111-111111111111"
OWNER_B = "22222222-2222-4222-8222-222222222222"


def local_endpoint(endpoint):
    return isinstance(endpoint, str) and endpoint.startswith(("unix:///", "npipe:////./pipe/"))


def port_value(value):
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("Port must be an integer") from None
    if not 1024 <= port <= 65535:
        raise argparse.ArgumentTypeError("Port must be between 1024 and 65535")
    return port


def clean_env(source):
    # No inherited service credentials, fixture overrides, Docker target overrides,
    # or Compose configuration overrides. Preserve only host runtime necessities.
    allowed = {"PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "COMSPEC",
               "PATHEXT", "TEMP", "TMP", "TMPDIR", "APPDATA", "LOCALAPPDATA",
               "LANG", "LC_ALL", "XDG_RUNTIME_DIR", "XDG_CONFIG_HOME",
               "DOCKER_CONFIG", "DOCKER_CLI_PLUGIN_EXTRA_DIRS"}
    return {k: v for k, v in source.items() if k.upper() in allowed}


def call(args, env, *, capture=False, check=True):
    return subprocess.run(args, cwd=ROOT, env=env, check=check, text=True,
                          stdout=subprocess.PIPE if capture else None)


def docker_target(env):
    if os.environ.get("DOCKER_HOST") or os.environ.get("DOCKER_CONTEXT"):
        raise ValueError("Unset Docker target overrides; select a local context explicitly")
    context = call(["docker", "context", "show"], env, capture=True).stdout.strip()
    if not context:
        raise ValueError("No Docker context")
    docker = ["docker", "--context", context]
    data = json.loads(call(docker + ["context", "inspect", context], env, capture=True).stdout)
    if len(data) != 1 or not local_endpoint(data[0]["Endpoints"]["docker"]["Host"]):
        raise ValueError("Refusing non-local Docker endpoint")
    if call(docker + ["info", "--format", "{{.OSType}}"], env, capture=True).stdout.strip() != "linux":
        raise ValueError("Linux container engine required")
    return docker


def fixture_env(env, project, port):
    a, b = secrets.token_hex(24), secrets.token_hex(24)
    password, signing = secrets.token_hex(24), secrets.token_hex(32)
    image = project + ":local"
    result = dict(env, SYNORA_SMOKE_IMAGE=image, SYNORA_SMOKE_PASSWORD=password,
                  SYNORA_SMOKE_SIGNING_KEY=signing, SYNORA_SMOKE_PORT=str(port),
                  SYNORA_SMOKE_TOKENS=json.dumps({a: OWNER_A, b: OWNER_B}))
    # GitHub only: mask synthetic credentials before any subprocess can emit them.
    if os.environ.get("GITHUB_ACTIONS") == "true":
        for value in (a, b, password, signing, result["SYNORA_SMOKE_TOKENS"]):
            print("::add-mask::" + value, flush=True)
    return result, a, b


def verify_runtime(docker, compose, env):
    for service, limit in (("api", 512 * 1024**2), ("worker", 768 * 1024**2)):
        cid = call(compose + ["ps", "-q", service], env, capture=True).stdout.strip()
        if not cid:
            raise ValueError("Missing runtime container: " + service)
        # Inspect only in memory; never print full container config or environment.
        info = json.loads(call(docker + ["inspect", cid], env, capture=True).stdout)[0]
        config, host = info["Config"], info["HostConfig"]
        if (not info["State"]["Running"] or config["User"] != "10001:10001"
                or not host["ReadonlyRootfs"] or host["Memory"] != limit
                or host.get("DeviceRequests") or host.get("Devices")
                or host["Privileged"] or "ALL" not in host["CapDrop"]
                or host["PidsLimit"] != 128 or host["NanoCpus"] <= 0):
            raise ValueError("Runtime resource/security policy failed: " + service)
    print("Verified non-root, read-only, CPU/memory/pid-limited API and worker; no GPU devices", flush=True)


def run(port):
    if sys.version_info[:2] != (3, 12):
        raise ValueError("Use Python 3.12 and the existing hash-locked QA environment")
    import importlib.util
    if any(importlib.util.find_spec(module) is None for module in ("pytest", "httpx")):
        raise ValueError("Install tests/requirements-dev.lock in a dedicated QA venv first")
    env = clean_env(os.environ)
    docker = docker_target(env)
    project = "synora-smoke-" + secrets.token_hex(6)
    env, a, b = fixture_env(env, project, port)
    image = env["SYNORA_SMOKE_IMAGE"]
    print("Disposable project: " + project, flush=True)
    with tempfile.TemporaryDirectory(prefix="synora-smoke-") as tmp:
        directory = Path(tmp)
        empty_env = directory / "empty.env"
        empty_env.touch()
        compose = docker + ["compose", "--env-file", str(empty_env), "-p", project,
                            "-f", str(ROOT / "infrastructure/compose.smoke.yaml")]
        # Fresh randomized project and tag. Refuse if a project already exists.
        if call(compose + ["ps", "-a", "-q"], env, capture=True).stdout.strip():
            raise ValueError("Refusing existing Compose project")
        try:
            call(compose + ["config", "--quiet"], env)
            call(compose + ["build", "api"], env)
            call(compose + ["up", "-d", "--no-build", "--wait", "--wait-timeout", "120"], env)
            verify_runtime(docker, compose, env)
            test_env = dict(clean_env(os.environ), SYNORA_QA_REQUIRE_LIVE="1",
                            SYNORA_QA_FIXTURE_POSTS="1",
                            SYNORA_QA_API_URL="http://127.0.0.1:" + str(port),
                            SYNORA_QA_TOKEN_A=a, SYNORA_QA_TOKEN_B=b)
            report = directory / "smoke.xml"
            call([sys.executable, "-m", "pytest", "-q", "-rs", "--tb=no", "--show-capture=no",
                  "tests/integration/test_live_api.py", "--junitxml=" + str(report)], test_env)
            call([sys.executable, "infrastructure/ci/assert-no-skips.py", str(report)], test_env)
            verify_runtime(docker, compose, env)
        finally:
            # Never use global prune, existing Compose project names, or a remote context.
            down = call(compose + ["down", "--volumes", "--timeout", "10"], env, check=False)
            if down.returncode:
                print("Scoped cleanup failed; inspect disposable project " + project, file=sys.stderr)
                raise RuntimeError("Disposable Compose cleanup failed")
            # Remove only our unique local image tag, not shared base images.
            existing = call(docker + ["image", "ls", "-q", image], env, capture=True)
            if existing.stdout.strip():
                call(docker + ["image", "rm", image], env)
    print("Disposable CPU fixture smoke complete; scoped project and volumes removed", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-disposable", action="store_true",
                        help="authorize local image build and temporary containers/volumes")
    parser.add_argument("--port", type=port_value, default=18081)
    args = parser.parse_args()
    if not args.confirm_disposable:
        parser.error("Explicit --confirm-disposable required")
    try:
        run(args.port)
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        # Do not dump process env, full inspection data, or signed URLs.
        print("Local fixture smoke failed: " + type(exc).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
