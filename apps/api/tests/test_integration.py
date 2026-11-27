"""Run only against disposable migrated Postgres; never a live database."""
import os
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest

if os.getenv("SYNORA_DISPOSABLE_DB")!="1":
    pytest.skip("explicit disposable database required",allow_module_level=True)
from synora import db
from synora.worker import run_one
from synora.config import settings
from synora.api import app, user
from fastapi.testclient import TestClient

SPEC=dict(prompt="Original melody",mode="instrumental",genres=[],moods=[],instruments=[],duration_seconds=15,bpm=None,lyrics=None,language=None)

@pytest.fixture(autouse=True)
def safety():
    assert settings.environment=="test" and settings.provider=="fixture"
    assert settings.database_url
    # Unique owners; no destructive cleanup of any database.

def test_idempotency_concurrent_and_ownership():
    uid=uuid4()
    with ThreadPoolExecutor(max_workers=5) as pool:
        rows=list(pool.map(lambda _:db.submit(uid,"same",SPEC),range(5)))
    assert len({x["id"] for x in rows})==1
    assert db.owned_job(uuid4(),rows[0]["id"]) is None
    with pytest.raises(db.Conflict):
        db.submit(uid,"same",SPEC|{"prompt":"other"})
    with db.db() as c:
        assert c.execute("select count(*) as n from synora.credit_reservations where job_id=%s",(rows[0]["id"],)).fetchone()["n"]==1
    db.cancel(uid,rows[0]["id"])

def test_rate_and_cancel():
    uid=uuid4()
    jobs=[db.submit(uid,str(i),SPEC) for i in range(3)]
    with pytest.raises(db.RateLimited): db.submit(uid,"four",SPEC)
    for job in jobs:
        assert db.cancel(uid,job["id"])["status"]=="cancelled"

def test_expired_fencing_and_retry():
    uid=uuid4()
    job=db.submit(uid,"lease",SPEC)
    row=db.claim()
    assert row["id"]==job["id"]
    with db.db() as c:
        c.execute("update synora.jobs set lease_until=now()-interval '1 second' where id=%s",(job["id"],))
    assert not db.progress(job["id"],row["lease_token"],90)
    assert not db.complete(job["id"],row["lease_token"],"unused",15,{})
    db.claim()  # requeue with delay
    with db.db() as c:
        c.execute("update synora.jobs set available_at=now() where id=%s",(job["id"],))
    new=db.claim()
    assert new["id"]==job["id"] and new["lease_token"]!=row["lease_token"]
    assert new["attempts"]==2
    db.cancel(uid,job["id"])
    assert not db.progress(job["id"],new["lease_token"],90)

def test_api_fixture_playback_and_cross_owner():
    uid=uuid4()
    app.dependency_overrides[user]=lambda:uid
    client=TestClient(app)
    try:
        res=client.post("/v1/music/jobs",json=SPEC,headers={"Idempotency-Key":"api"})
        assert res.status_code==202,res.text
        job=res.json()["id"]
        assert run_one()
        completed=client.get(f"/v1/jobs/{job}").json()
        assert completed["status"]=="succeeded" and completed["simulated"]
        asset=completed["asset_id"]
        meta=client.get(f"/v1/assets/{asset}").json()
        assert meta["simulated"] and meta["mime_type"]=="audio/wav"
        assert client.get(meta["url"]).content[:4]==b"RIFF"
        assert client.get(meta["url"]+"bad").status_code==403
        app.dependency_overrides[user]=lambda:uuid4()
        assert client.get(f"/v1/jobs/{job}").status_code==404
        assert client.get(f"/v1/assets/{asset}").status_code==404
    finally:
        app.dependency_overrides.clear()
