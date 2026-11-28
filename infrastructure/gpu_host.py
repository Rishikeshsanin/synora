"""Optional offline ACE research host checks. No downloads, cloud calls, servers or model loading.

The CPU application environment is deliberately separate. A successful check is
not inference evidence, a license certification, a billing guarantee or a sandbox.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
from tempfile import TemporaryFile

ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / "infrastructure/gpu/profile.json").read_text())
MAX_JSON = 8 * 1024 * 1024


class Blocked(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Blocked(message)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_JSON,
            "Expected bounded regular JSON evidence file")
    return json.loads(path.read_text(encoding="utf-8"))


def private_dir(path):
    path = Path(path)
    require(path.is_absolute() and path.exists() and path.is_dir() and path.resolve() == path,
            "Workspace must be an existing absolute non-symlink directory")
    require(not path.is_relative_to(ROOT) and not ROOT.is_relative_to(path),
            "Workspace must be separate from Synora source")
    require(os.name == "posix" and path.stat().st_uid == os.getuid()
            and stat.S_IMODE(path.stat().st_mode) & 0o077 == 0,
            "Linux/POSIX owner-private workspace (0700) required")
    return path


def private_file(path, workspace):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and path.is_relative_to(workspace)
            and path.is_file() and path.stat().st_uid == os.getuid()
            and stat.S_IMODE(path.stat().st_mode) & 0o077 == 0,
            "Evidence must be an owner-private regular workspace file")
    return path


def offline_env(source, workspace, gpu_index="0"):
    # Deliberately do not inherit provider tokens, proxy settings, Python injection,
    # cloud credentials, or an arbitrary PATH/HOME. Host sandbox still required.
    allowed = {"PATH", "LANG", "LC_ALL", "LD_LIBRARY_PATH"}
    env = {k: v for k, v in source.items() if k in allowed}
    for name in ("home", "hf", "tmp", "cache"):
        p = workspace / name
        p.mkdir(mode=0o700, exist_ok=True)
        require(p.resolve() == p and p.stat().st_uid == os.getuid()
                and stat.S_IMODE(p.stat().st_mode) & 0o077 == 0,
                "Private cache path invalid")
    env.update(HOME=str(workspace / "home"), HF_HOME=str(workspace / "hf"),
               XDG_CACHE_HOME=str(workspace / "cache"), TMPDIR=str(workspace / "tmp"),
               HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
               HF_HUB_DISABLE_IMPLICIT_TOKEN="1", HF_DATASETS_OFFLINE="1",
               CUDA_VISIBLE_DEVICES=str(gpu_index), OMP_NUM_THREADS=str(PROFILE["cpu_threads"]),
               MKL_NUM_THREADS=str(PROFILE["cpu_threads"]), OPENBLAS_NUM_THREADS=str(PROFILE["cpu_threads"]),
               PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", SYNORA_ENV="local")
    return env


def capture(args, env, cwd, timeout=30):
    # Never echo subprocess stdout/stderr, command arguments or environment.
    try:
        # Keep potentially large stdout out of RAM and never persist inspection logs.
        with TemporaryFile(dir=cwd) as output:
            subprocess.run(args, cwd=cwd, env=env, stdout=output,
                           stderr=subprocess.DEVNULL, timeout=timeout, check=True)
            require(output.tell() <= MAX_JSON, "Inspection output exceeds bound")
            output.seek(0)
            return output.read(MAX_JSON + 1).decode("utf-8").strip()
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise Blocked("Required local inspection command failed") from None


def inspect_source(source, snapshot, workspace, env):
    source, snapshot = Path(source), Path(snapshot)
    require(source.is_absolute() and source.resolve() == source and source.is_dir()
            and not source.is_relative_to(workspace) and not workspace.is_relative_to(source),
            "ACE source must be a separate absolute directory")
    require(snapshot.is_absolute() and snapshot.resolve() == snapshot and snapshot.is_dir()
            and snapshot.name == PROFILE["snapshot_revision"] and snapshot.parent.name == "snapshots",
            "Use the exact pinned HF snapshot directory")
    cache = snapshot.parent.parent
    require(not workspace.is_relative_to(cache) and not cache.is_relative_to(workspace)
            and not source.is_relative_to(cache) and not cache.is_relative_to(source),
            "Keep source, upstream cache and private output separate")
    require(capture(["git", "-C", str(source), "rev-parse", "HEAD"], env, workspace)
            == PROFILE["code_revision"], "ACE source revision mismatch")
    require(not capture(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=normal"],
                        env, workspace), "ACE source checkout is not clean")
    files = {}
    for path in sorted(snapshot.rglob("*")):
        require(not path.is_symlink() or (path.resolve().is_file() and path.resolve().is_relative_to(cache / "blobs")),
                "Unexpected snapshot symlink")
        if path.is_file() and path.suffix in (".safetensors", ".bin"):
            files[str(path.relative_to(snapshot))] = path.stat().st_size
    require(files and all(size > 0 for size in files.values()), "No usable cached checkpoint files")
    require((snapshot / PROFILE["model"]).is_dir(), "Expected model missing from snapshot")
    license_path = source / "LICENSE"
    lock_path = source / "uv.lock"
    require(license_path.is_file() and lock_path.is_file(), "Pinned source license or lock missing")
    model_license = next((snapshot / name for name in ("LICENSE", "LICENSE.md", "README.md")
                          if (snapshot / name).is_file()), None)
    require(model_license is not None, "Model license/card absent from snapshot")
    return {"code_revision": PROFILE["code_revision"], "snapshot_revision": PROFILE["snapshot_revision"],
            "source_license_sha256": sha(license_path), "upstream_lock_sha256": sha(lock_path),
            "model_license_document_sha256": sha(model_license),
            "weight_files": len(files), "weight_bytes": sum(files.values()),
            "weight_content_verified": False, "source_license_reviewed": False}


def normalize(name):
    require(isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", name),
            "Malformed package name")
    return re.sub(r"[-_.]+", "-", name).lower()


def inventory(python, source, env, workspace):
    require(python.is_absolute() and python.is_file(), "Specify the upstream environment Python")
    script = """import importlib.metadata as m,importlib.util,json,sys
spec=importlib.util.find_spec("acestep")
print(json.dumps({"python":list(sys.version_info[:2]),"prefix":sys.prefix,"base_prefix":sys.base_prefix,"ace_origin":spec.origin if spec else None,"packages":[{"name":d.metadata["Name"],"version":d.version,"license":d.metadata.get("License-Expression") or d.metadata.get("License") or "UNKNOWN"} for d in m.distributions()]}))
"""
    data = json.loads(capture([str(python), "-I", "-c", script], env, workspace))
    require(data["python"] == [3, 12] and data["prefix"] != data["base_prefix"],
            "Separate upstream Python 3.12 virtual environment required")
    prefix = Path(data["prefix"]).resolve()
    require(prefix.is_relative_to(source) and not prefix.is_relative_to(ROOT)
            and data["ace_origin"] and Path(data["ace_origin"]).resolve().is_relative_to(source / "acestep"),
            "Installed ACE must import from the pinned checkout, not an unrelated wheel")
    entries = {}
    for item in data["packages"]:
        name = normalize(item["name"])
        require(name not in entries, "Duplicate upstream distribution")
        entries[name] = {"version": item["version"], "license": item["license"][:2000]}
    require("torch" in entries and "ace-step" in entries, "ACE and torch not installed in target environment")
    digest = hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return entries, digest


def verify_audit(audit, installed, reviewed_local):
    """Validate an existing separate-environment pip-audit JSON, never query online."""
    require(isinstance(audit, dict) and isinstance(audit.get("dependencies"), list),
            "Expected pip-audit JSON dependency list")
    seen = set()
    for dep in audit["dependencies"]:
        name = normalize(dep.get("name"))
        require(name in installed and name not in seen, "Audit inventory mismatch")
        seen.add(name)
        if dep.get("skip_reason"):
            # Local pinned source packages are not PyPI distributions. They still
            # need explicit human review; no skip allowed for registry dependencies.
            require(not dep.get("vulns") and name in {"ace-step", "nano-vllm"} and name in reviewed_local
                    and reviewed_local[name] == installed[name]["version"],
                    "Unaudited package in upstream environment")
        else:
            require(dep.get("version") == installed[name]["version"]
                    and isinstance(dep.get("vulns"), list) and not dep["vulns"],
                    "Vulnerable or version-mismatched upstream dependency")
    require(seen == set(installed), "Audit does not cover full installed inventory")
    return {"audited_packages": len(seen), "local_source_reviews": sorted(reviewed_local),
            "audit_revalidated_online": False}


def verify_review(review, audit_file, digest, source_info, installed):
    audit_data = read_json(audit_file)
    require(review.get("research_only") is True and review.get("commercial_release_approved") is False
            and review.get("reviewed") is True and review.get("inventory_sha256") == digest
            and review.get("audit_sha256") == sha(audit_file), "Missing or stale explicit research review")
    for key in ("code_revision", "snapshot_revision", "source_license_sha256",
                "upstream_lock_sha256", "model_license_document_sha256"):
        require(review.get(key) == source_info[key], "License/source review does not match pinned files")
    # The license inventory may contain UNKNOWN or non-standard strings; require
    # owner-reviewed dispositions for every distribution, not automated clearance.
    dispositions = review.get("package_license_review", {})
    require(isinstance(dispositions, dict) and set(dispositions) == set(installed)
            and all(v in ("reviewed-research-only",) for v in dispositions.values()),
            "Every upstream package license requires research-only review")
    local = review.get("reviewed_local_packages", {})
    require(isinstance(local, dict) and set(local) <= {"ace-step", "nano-vllm"},
            "Unexpected local-package audit exemption")
    return verify_audit(audit_data, installed, local)


def save_inventory(workspace, installed):
    """Reuse an identical private inventory; refuse stale or unsafe existing files."""
    target = workspace / "inventory.json"
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError:
        require(read_json(private_file(target, workspace)) == installed,
                "Installed inventory changed; use a new reviewed workspace")
        return
    with os.fdopen(fd, "w") as stream:
        json.dump(installed, stream, indent=2)


def memory_gate(total, free, available):
    require(total >= PROFILE["min_gpu_total_mib"] and free >= PROFILE["min_gpu_free_mib"],
            "Insufficient GPU headroom; never use MX330 2 GB for this profile")
    require(available >= PROFILE["min_host_available_mib"], "Insufficient host RAM for offload")


def hardware(env, workspace, gpu_index):
    require(re.fullmatch(r"[0-9]{1,3}", str(gpu_index)) is not None, "Invalid GPU index")
    raw = capture(["nvidia-smi", "--id=" + str(gpu_index),
                   "--query-gpu=memory.total,memory.free", "--format=csv,noheader,nounits"],
                  env, workspace, timeout=15)
    require(len(raw.splitlines()) == 1, "Exactly one GPU must be selected")
    try:
        total, free = map(int, raw.split(","))
        available = next(int(line.split()[1]) // 1024 for line in Path("/proc/meminfo").read_text().splitlines()
                         if line.startswith("MemAvailable:"))
    except (ValueError, StopIteration, OSError):
        raise Blocked("Unable to inspect host memory") from None
    memory_gate(total, free, available)
    require(shutil.disk_usage(workspace).free // 1024**2 >= PROFILE["min_workspace_free_mib"],
            "Insufficient private workspace disk")
    return {"gpu_total_mib": total, "gpu_free_mib": free, "host_available_mib": available,
            "cuda_inference_verified": False}


@contextmanager
def session_lease(workspace):
    """One exclusive local process session; never reclaim an ambiguous stale lock."""
    lease = workspace / "session.lock"
    try:
        fd = os.open(lease, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError:
        raise Blocked("Existing session lock; verify old process is stopped before manual removal") from None
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(str(os.getpid()) + "\n")
        yield
    finally:
        lease.unlink()


def run_bounded(argv, env, workspace, seconds):
    """Local subprocess lifecycle primitive for a reviewed benchmark integration.

    No public CLI dispatch to arbitrary argv. No raw prompts, tokens or upstream
    logs are emitted. A process group is terminated on timeout/interruption.
    A host cgroup/network sandbox must be imposed externally; not a hard VRAM cap.
    """
    require(type(seconds) is int and 1 <= seconds <= PROFILE["max_session_seconds"],
            "Invalid warm-session deadline")
    require(os.name == "posix", "POSIX process group required")
    with session_lease(workspace):
        started = time.monotonic()
        process = subprocess.Popen(argv, cwd=workspace, env=env, start_new_session=True,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        try:
            returncode = process.wait(timeout=seconds)
            require(returncode == 0, "Local session process failed")
            return {"status": "completed", "wall_seconds": round(time.monotonic() - started, 3)}
        except subprocess.TimeoutExpired:
            raise Blocked("Local warm-session deadline exceeded") from None
        finally:
            # Kill surviving group members even if the leader exited. No global GPU kill.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--ace-source", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--gpu-index", default="0")
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--authorized-local-gpu", action="store_true")
    parser.add_argument("--offline-host-confirmed", action="store_true")
    args = parser.parse_args()
    try:
        require(os.getenv("SYNORA_ENV") != "production", "Research profile forbidden in production")
        workspace = private_dir(args.workspace)
        require(args.authorized_local_gpu and args.offline_host_confirmed,
                "Explicit authorized host and external offline isolation confirmation required")
        env = offline_env(os.environ, workspace, args.gpu_index)
        source_info = inspect_source(args.ace_source, args.snapshot, workspace, env)
        installed, digest = inventory(args.python, args.ace_source, env, workspace)
        report = dict(source_info, inventory_sha256=digest, packages=len(installed),
                      generation_executed=False, commercial_release_approved=False,
                      ready_for_reviewed_benchmark=False, profile_generation_enabled=False)
        # Write private inventory for external license review; no raw license text or paths in console.
        save_inventory(workspace, installed)
        if args.audit is None or args.review is None:
            report["blocker"] = "Separate environment audit and reviewed license dispositions required"
            print(json.dumps(report, indent=2))
            return 2
        audit = private_file(args.audit, workspace)
        review = private_file(args.review, workspace)
        report.update(verify_review(read_json(review), audit, digest, source_info, installed))
        # uv pip check reads the existing upstream environment; never sync/install.
        capture(["uv", "--offline", "pip", "check", "--python", str(args.python)],
                env, workspace, timeout=60)
        report["upstream_dependency_consistency"] = "passed"
        report["source_license_reviewed"] = True
        report.update(hardware(env, workspace, args.gpu_index))
        report["ready_for_reviewed_benchmark"] = True
        print(json.dumps(report, indent=2))
        return 0
    except (Blocked, OSError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"generation_executed": False, "ready_for_reviewed_benchmark": False,
                          "blocker": str(exc) if isinstance(exc, Blocked) else type(exc).__name__}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
