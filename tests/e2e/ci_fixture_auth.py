"""Disposable CI auth boundary for native browser acceptance, never production Auth.

The browser uses the actual Supabase client with pre-seeded synthetic sessions;
API authorization, queue, worker, library, media and downloads are real fixture
services. The loopback stub implements only user lookup and logout. It does not
prove real Supabase OTP, JWT verification or provider-side token revocation.
"""
import json
import os
import stat
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

WEB = "http://127.0.0.1:3000"
API = "http://127.0.0.1:8000"
AUTH = "http://127.0.0.1:19090"


def configuration():
    if (os.getenv("GITHUB_ACTIONS") != "true"
            or os.getenv("SYNORA_ENV") != "test"
            or os.getenv("SYNORA_DISPOSABLE_DB") != "1"
            or os.getenv("MUSIC_PROVIDER") != "fixture"
            or os.getenv("SYNORA_REAL_GENERATION_ENABLED") != "false"
            or os.getenv("SYNORA_QA_FIXTURE_POSTS") != "1"
            or os.getenv("SYNORA_QA_API_URL") != API
            or os.getenv("SYNORA_QA_WEB_URL") != WEB
            or os.getenv("NEXT_PUBLIC_SUPABASE_URL") != AUTH):
        raise RuntimeError("Refusing non-disposable or non-loopback fixture environment")
    mapping = json.loads(os.environ["FIXTURE_TOKENS_JSON"])
    tokens = tuple(os.environ[k] for k in ("SYNORA_QA_TOKEN_A", "SYNORA_QA_TOKEN_B"))
    owners = tuple(str(UUID(mapping[t])) for t in tokens)
    if len(set(tokens)) != 2 or len(set(owners)) != 2 or not all(tokens):
        raise RuntimeError("Two distinct test accounts required")
    return dict(zip(tokens, owners))


def user(owner):
    return {
        "id": owner, "aud": "authenticated", "role": "authenticated",
        "email": "fixture-" + owner[:8] + "@example.invalid",
        "app_metadata": {"provider": "email", "providers": ["email"]},
        "user_metadata": {}, "created_at": "2025-01-01T00:00:00Z",
        "email_confirmed_at": "2025-01-01T00:00:00Z",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "is_anonymous": False, "identities": [],
    }


def serve(accounts):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def respond(self, status, payload=None):
            body = json.dumps(payload).encode() if payload is not None else b""
            self.send_response(status)
            if self.headers.get("Origin") == WEB:
                self.send_header("Access-Control-Allow-Origin", WEB)
                self.send_header("Access-Control-Allow-Headers",
                                 "authorization, apikey, content-type, x-client-info, x-supabase-api-version")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Vary", "Origin")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def principal(self):
            value = self.headers.get("Authorization", "")
            return accounts.get(value[7:]) if value.startswith("Bearer ") else None

        def do_OPTIONS(self):
            self.respond(204 if self.headers.get("Origin") == WEB else 403)

        def do_GET(self):
            if self.path == "/health":
                self.respond(200, {"status": "fixture-only"})
            elif urlsplit(self.path).path == "/auth/v1/user" and self.principal():
                self.respond(200, user(self.principal()))
            else:
                self.respond(401, {"message": "Unknown fixture principal"})

        def do_POST(self):
            if urlsplit(self.path).path == "/auth/v1/logout" and self.principal():
                self.respond(204)
            else:
                self.respond(403, {"message": "Unsupported fixture auth operation"})

    ThreadingHTTPServer(("127.0.0.1", 19090), Handler).serve_forever()


def write_states(accounts):
    temp = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    for label, (token, owner) in zip(("a", "b"), accounts.items()):
        path = temp / ("synora-browser-" + label + ".json")
        session = {
            "access_token": token, "token_type": "bearer",
            "refresh_token": "fixture-only-" + str(uuid4()),
            "expires_in": 3600, "expires_at": int(time.time()) + 3600,
            "user": user(owner),
        }
        # Supabase JS default key derives from the first hostname segment.
        key = "sb-" + urlsplit(AUTH).hostname.split(".")[0] + "-auth-token"
        state = {"cookies": [], "origins": [{"origin": WEB, "localStorage": [
            {"name": key, "value": json.dumps(session)}
        ]}]}
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(state, f)
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise RuntimeError("Fixture state must be private")


def seed(accounts):
    token = next(iter(accounts))

    def request(path, data=None):
        headers = {"Authorization": "Bearer " + token}
        if data is not None:
            headers.update({"Content-Type": "application/json", "Idempotency-Key": str(uuid4())})
        req = Request(API + path, headers=headers,
                      data=json.dumps(data).encode() if data is not None else None)
        with urlopen(req, timeout=10) as response:
            return response.status, json.load(response)

    status, job = request("/v1/music/jobs", {
        "prompt": "Original persisted CI fixture", "mode": "instrumental",
        "genres": [], "moods": [], "instruments": [], "duration_seconds": 15,
        "bpm": None, "lyrics": None, "language": None,
    })
    if status != 202:
        raise RuntimeError("Fixture job not accepted")
    job_id = str(UUID(job["id"]))
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        status, job = request("/v1/jobs/" + job_id)
        if status != 200:
            raise RuntimeError("Cannot read seeded job")
        if job["status"] == "succeeded":
            if job.get("simulated") is not True or not job.get("asset_id"):
                raise RuntimeError("Expected genuine fixture-worker output")
            print(job_id)
            return
        if job["status"] in ("failed", "cancelled"):
            raise RuntimeError("Seeded job did not complete")
        time.sleep(0.5)
    raise RuntimeError("Seeded job timed out")


if __name__ == "__main__":
    accounts = configuration()
    if sys.argv[1:] == ["serve"]:
        serve(accounts)
    elif sys.argv[1:] == ["prepare"]:
        write_states(accounts)
        seed(accounts)
    else:
        raise SystemExit("Expected serve or prepare")
