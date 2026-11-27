"""Strict disposable Postgres acceptance. Never run against shared/live resources."""
import os
from urllib.parse import urlparse, parse_qs
from uuid import uuid4
import hashlib
import io
import wave
import pytest

SPEC = dict(prompt="Independent original fixture", mode="instrumental", genres=[],
            moods=[], instruments=[], duration_seconds=15, bpm=None, lyrics=None, language=None)


@pytest.fixture
def stack():
    if os.getenv("SYNORA_QA_DISPOSABLE_DB") != "1":
        if os.getenv("SYNORA_QA_REQUIRE_DB") == "1":
            pytest.fail("Disposable DB authorization missing")
        pytest.skip("Disposable database not configured")
    from synora import db, worker, storage
    from synora.config import settings
    from synora.api import app
    from fastapi.testclient import TestClient
    import json
    assert settings.environment == "test" and settings.provider == "fixture"
    url = urlparse(settings.database_url)
    assert url.hostname in ("localhost", "127.0.0.1", "::1")
    assert url.path in ("/synora_dev", "/synora_qa")
    assert not settings.supabase_url and not settings.storage_key
    tokens = json.loads(settings.fixture_tokens)
    a, b = os.environ["SYNORA_QA_TOKEN_A"], os.environ["SYNORA_QA_TOKEN_B"]
    assert a != b and tokens[a] != tokens[b]
    with db.db() as c:
        assert c.execute("select count(*) as n from synora.jobs where status in ('queued','running')").fetchone()["n"] == 0
    with TestClient(app) as client:
        yield db, worker, storage, client, {"Authorization": "Bearer "+a}, {"Authorization": "Bearer "+b}


def submit(client, headers, key=None):
    response = client.post("/v1/music/jobs", json=SPEC,
                           headers=headers | {"Idempotency-Key": key or str(uuid4())})
    assert response.status_code == 202, response.status_code
    return response.json()["id"]


def state(db, job):
    with db.db() as c:
        return c.execute("""select j.status,j.attempts,j.asset_id,r.status as reservation,
            (select count(*) from synora.assets a where a.job_id=j.id) as assets
            from synora.jobs j join synora.credit_reservations r on r.job_id=j.id
            where j.id=%s""",(job,)).fetchone()


def test_two_bearer_identities_cancel_recover_and_signed_media(stack, monkeypatch):
    db, worker, storage, client, a, b = stack
    key = str(uuid4())
    cancelled = submit(client, a, key)
    assert submit(client, a, key) == cancelled
    other = submit(client, b, key)
    assert other != cancelled
    for headers in (b, {}, {"Authorization":"Bearer invalid-qa-token"}):
        assert client.get("/v1/jobs/"+cancelled, headers=headers).status_code in (401,403,404)
        assert client.post("/v1/jobs/"+cancelled+"/cancel", headers=headers).status_code in (401,403,404)
    claim = db.claim()
    assert str(claim["id"]) == cancelled
    assert client.post("/v1/jobs/"+cancelled+"/cancel",headers=a).json()["status"] == "cancelled"
    assert not db.progress(claim["id"],claim["lease_token"],95)
    assert not db.complete(claim["id"],claim["lease_token"],"unused",15,{})
    assert state(db,cancelled)["reservation"] == "released"
    assert state(db,cancelled)["assets"] == 0

    lease = db.claim()
    assert str(lease["id"]) == other
    with db.db() as c:
        c.execute("update synora.jobs set lease_until=now()-interval '1 second' where id=%s",(other,))
    assert not db.progress(lease["id"],lease["lease_token"],95)
    assert not db.complete(lease["id"],lease["lease_token"],"unused",15,{})
    assert db.claim() is None
    with db.db() as c:
        c.execute("update synora.jobs set available_at=now() where id=%s",(other,))
    assert worker.run_one()
    completed = state(db,other)
    assert (completed["status"],completed["attempts"],completed["reservation"],completed["assets"]) == ("succeeded",2,"settled",1)
    asset = str(completed["asset_id"])
    assert client.get("/v1/assets/"+asset,headers=a).status_code == 404
    assert client.get("/v1/assets/"+asset).status_code == 401
    meta = client.get("/v1/assets/"+asset,headers=b).json()
    assert meta["simulated"] is True
    signed = meta["url"]
    parsed = urlparse(signed)
    relative = parsed.path+"?"+parsed.query
    response = client.get(relative)
    assert response.status_code == 200
    with wave.open(io.BytesIO(response.content)) as wav:
        assert wav.getnframes()/wav.getframerate() == 15
        assert len(wav.readframes(wav.getnframes())) > 0
    download = client.get("/v1/assets/"+asset+"?download=true",headers=b).json()
    p = urlparse(download["url"])
    downloaded = client.get(p.path+"?"+p.query)
    assert downloaded.status_code == 200
    assert "attachment" in downloaded.headers["content-disposition"]
    assert hashlib.sha256(downloaded.content).digest() == hashlib.sha256(response.content).digest()
    assert client.get(relative+"x").status_code == 403
    expiry = int(parse_qs(parsed.query)["expires"][0])
    from types import SimpleNamespace
    monkeypatch.setattr(storage,"time",SimpleNamespace(time=lambda: expiry+1))
    assert client.get(relative).status_code == 403
    assert client.post("/v1/jobs/"+other+"/cancel",headers=b).json()["status"] == "succeeded"


def test_rejected_settlement_does_not_leave_orphan(stack, monkeypatch):
    db, worker, storage, client, a, _ = stack
    job = submit(client,a)
    actual_complete = db.complete
    def cancel_before_complete(job_id, token, key, duration, provenance, *args, **kwargs):
        with db.db() as c:
            owner = c.execute("select user_id from synora.jobs where id=%s",(job_id,)).fetchone()["user_id"]
        db.cancel(owner,job_id)
        return actual_complete(job_id,token,key,duration,provenance,*args,**kwargs)
    monkeypatch.setattr(db,"complete",cancel_before_complete)
    assert worker.run_one()
    assert state(db,job)["status"] == "cancelled"
    assert state(db,job)["assets"] == 0
    assert state(db,job)["reservation"] == "released"
    assert not list(storage.settings.media_dir.glob("*/"+job+"/*.wav")), "Rejected settlement left orphan media"
