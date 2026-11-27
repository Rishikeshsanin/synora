"""HTTP error contract regressions with no external services or database writes."""
from contextlib import contextmanager
from dataclasses import replace
import json
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from synora import api, db

SPEC = dict(prompt="Original fixture", mode="instrumental", genres=[], moods=[],
            instruments=[], duration_seconds=15, bpm=None, lyrics=None, language=None)


def assert_error(response, status, code, message):
    assert response.status_code == status
    payload = response.json()
    assert set(payload) == {"code", "message", "request_id"}
    assert payload["code"] == code
    assert payload["message"] == message
    assert str(UUID(payload["request_id"])) == payload["request_id"]
    assert response.headers["x-request-id"] == payload["request_id"]
    assert response.headers["cache-control"] == "no-store"
    return payload["request_id"]


@pytest.fixture
def client_and_headers(monkeypatch, tmp_path):
    owner = uuid4()
    token = str(uuid4())
    # Explicit local fixture identity, with no remote authentication requests.
    monkeypatch.setattr(api, "settings", replace(
        api.settings, environment="test", provider="fixture",
        fixture_tokens=json.dumps({token: str(owner)}),
        supabase_url="", supabase_key="", media_dir=tmp_path,
        signing_key="x"*32, public_url="http://testserver"))
    with TestClient(api.app) as client:
        yield client, {"Authorization": "Bearer "+token, "Idempotency-Key": "regression"}


def test_auth_and_framework_errors(client_and_headers):
    client, _ = client_and_headers
    path = "/v1/music/library"
    first = assert_error(client.get(path), 401, "unauthorized", "Bearer token required")
    second = assert_error(client.get(path, headers={"Authorization": "Bearer invalid"}),
                          401, "unauthorized", "Invalid token")
    assert first != second
    assert_error(client.get("/not-a-route"), 404, "http_error", "Request failed")
    method = client.delete("/health")
    assert_error(method, 405, "http_error", "Request failed")
    assert "GET" in method.headers["allow"]


def test_validation_and_oversized_body(client_and_headers):
    client, headers = client_and_headers
    assert_error(client.post("/v1/music/jobs", headers=headers, json=SPEC | {"duration_seconds": 1}),
                 422, "invalid_request", "Request validation failed")
    oversized = client.post("/v1/music/jobs", headers=headers | {"Content-Type": "application/json"},
                            content=b"x"*32769)
    assert_error(oversized, 413, "body_too_large", "Request too large")


@pytest.mark.parametrize(("failure", "status", "code", "message"), [
    (db.Conflict, 409, "idempotency_conflict", "Key already used for a different request"),
    (db.RateLimited, 429, "rate_limited", "Generation limit reached"),
])
def test_admission_error_contract(client_and_headers, monkeypatch, failure, status, code, message):
    client, headers = client_and_headers
    def reject(*args):
        raise failure("internal detail must stay private")
    monkeypatch.setattr(db, "submit", reject)
    assert_error(client.post("/v1/music/jobs", headers=headers, json=SPEC), status, code, message)


def test_ready_preserves_explicit_provider_error(client_and_headers, monkeypatch):
    client, _ = client_and_headers
    class Connection:
        def execute(self, *args):
            return None
    @contextmanager
    def ready_db():
        yield Connection()
    monkeypatch.setattr(db, "db", ready_db)
    monkeypatch.setattr(api, "settings", replace(api.settings, provider="disabled"))
    assert_error(client.get("/ready"), 503, "provider_disabled", "No approved provider")


def test_cursor_and_signed_media_error_contract(client_and_headers, monkeypatch):
    client, headers = client_and_headers
    def reject_cursor(*args):
        raise ValueError("private database detail")
    monkeypatch.setattr(db, "music_library", reject_cursor)
    assert_error(client.get("/v1/music/library", headers=headers, params={"cursor": str(uuid4())}),
                 422, "invalid_cursor", "Invalid library cursor")
    assert_error(client.get(f"/v1/media/{uuid4()}?expires=0&download=0&sig=bad"),
                 403, "forbidden", "Invalid or expired media URL")


def test_unexpected_error_redacts_exception(client_and_headers, monkeypatch):
    client, headers = client_and_headers
    def fail(*args):
        raise RuntimeError("PRIVATE_UNEXPECTED_DETAIL")
    monkeypatch.setattr(db, "music_library", fail)
    response = client.get("/v1/music/library", headers=headers)
    assert_error(response, 500, "internal_error", "Internal error")
    assert "PRIVATE_UNEXPECTED_DETAIL" not in response.text
