"""Fail-closed preflight for Issue #29. Never print tokens or storage contents."""
import json
import os
import stat
import sys
from pathlib import Path
from uuid import UUID


def validate(env):
    required = ("RUNNER_TEMP", "SYNORA_QA_TOKEN_A", "SYNORA_QA_TOKEN_B",
                "FIXTURE_TOKENS_JSON", "SYNORA_QA_STORAGE_STATE",
                "SYNORA_QA_STORAGE_STATE_B", "SYNORA_QA_FIXTURE_PAGE_URL",
                "SYNORA_QA_FIXTURE_JOB_ID", "SYNORA_QA_API_URL", "SYNORA_QA_WEB_URL")
    for name in required:
        if not env.get(name):
            raise ValueError("Missing required fixture setting: " + name)
    if (env["SYNORA_QA_WEB_URL"] != "http://127.0.0.1:3000"
            or env["SYNORA_QA_API_URL"] != "http://127.0.0.1:8000"
            or env["SYNORA_QA_FIXTURE_PAGE_URL"] != "http://127.0.0.1:3000/studio"):
        raise ValueError("Fixture URLs must be exact CI loopback origins")
    try:
        UUID(env["SYNORA_QA_FIXTURE_JOB_ID"])
        token_map = json.loads(env["FIXTURE_TOKENS_JSON"])
        tokens = [env["SYNORA_QA_TOKEN_A"], env["SYNORA_QA_TOKEN_B"]]
        owners = [UUID(token_map[t]) for t in tokens]
    except (KeyError, TypeError, ValueError):
        raise ValueError("Invalid fixture job or owner mapping") from None
    if tokens[0] == tokens[1] or owners[0] == owners[1]:
        raise ValueError("Two distinct fixture principals required")
    paths = [Path(env[k]).resolve() for k in ("SYNORA_QA_STORAGE_STATE", "SYNORA_QA_STORAGE_STATE_B")]
    if paths[0] == paths[1]:
        raise ValueError("Distinct storage state paths required")
    tmp = Path(env["RUNNER_TEMP"]).resolve()
    for path, token in zip(paths, tokens):
        if (not path.is_relative_to(tmp) or not path.is_file()
                or stat.S_IMODE(path.stat().st_mode) & 0o077
                or path.stat().st_size > 1024 * 1024
                or any(c in str(path) for c in "\r\n")):
            raise ValueError("Storage state must be a private bounded runner-temp file")
        try:
            state = json.loads(path.read_text())
            sessions = []
            for origin in state["origins"]:
                if origin["origin"] != env["SYNORA_QA_WEB_URL"]:
                    raise ValueError("Unexpected storage origin")
                for item in origin.get("localStorage", []):
                    if item["name"].endswith("-auth-token"):
                        sessions.append(json.loads(item["value"]))
            matches = [s for s in sessions if isinstance(s, dict) and s.get("access_token") == token]
        except (KeyError, TypeError, ValueError, OSError):
            raise ValueError("Malformed or unexpected storage state") from None
        if len(matches) != 1:
            raise ValueError("Storage session does not match assigned fixture bearer token")
    return True


if __name__ == "__main__":
    try:
        validate(os.environ)
    except ValueError as exc:
        print("::error::" + str(exc), file=sys.stderr)
        sys.exit(1)
    print("Two distinct private loopback browser states and seeded job configuration verified")
