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
from synora.api import app
from synora import api
from dataclasses import replace
import json
import time
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
    with pytest.raises(db.RateLimited):
        db.submit(uid,"four",SPEC)
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

def test_api_fixture_playback_and_cross_owner(monkeypatch):
    uid, other=uuid4(),uuid4()
    tokens={str(uuid4()):str(uid),str(uuid4()):str(other)}
    token_a,token_b=tokens
    monkeypatch.setattr(api,"settings",replace(settings,fixture_tokens=json.dumps(tokens),
                                              supabase_url="",supabase_key=""))
    client=TestClient(app)
    a={"Authorization":f"Bearer {token_a}"}
    b={"Authorization":f"Bearer {token_b}"}
    assert client.get("/health").status_code==200
    assert client.get("/ready").status_code==200
    assert client.get("/v1/music/capabilities").json()["simulated"] is True
    assert client.post("/v1/music/jobs",json=SPEC,headers={"Idempotency-Key":"missing"}).status_code==401
    assert client.post("/v1/music/jobs",json=SPEC,headers={"Authorization":"Bearer bogus","Idempotency-Key":"invalid"}).status_code==401
    res=client.post("/v1/music/jobs",json=SPEC,headers=a|{"Idempotency-Key":"api"})
    assert res.status_code==202,res.text
    job=res.json()["id"]
    same=client.post("/v1/music/jobs",json=SPEC,headers=a|{"Idempotency-Key":"api"})
    assert same.json()["id"]==job
    assert client.post("/v1/music/jobs",json=SPEC|{"prompt":"different"},headers=a|{"Idempotency-Key":"api"}).status_code==409
    assert client.get(f"/v1/jobs/{job}",headers=b).status_code==404
    assert client.post(f"/v1/jobs/{job}/cancel",headers=b).status_code==404
    assert run_one()
    completed=client.get(f"/v1/jobs/{job}",headers=a).json()
    assert completed["status"]=="succeeded" and completed["simulated"] and completed["progress"]==100
    asset=completed["asset_id"]
    meta=client.get(f"/v1/assets/{asset}",headers=a).json()
    assert meta["simulated"] and meta["mime_type"]=="audio/wav"
    assert client.get(meta["url"]).content[:4]==b"RIFF"
    assert client.get(meta["url"]+"bad").status_code==403
    assert client.get(f"/v1/assets/{asset}",headers=b).status_code==404
    dl=client.get(f"/v1/assets/{asset}?download=true",headers=a).json()
    assert "attachment" in client.get(dl["url"]).headers["content-disposition"]
    assert client.get(dl["url"].replace("download=1","download=0")).status_code==403
    from synora.storage import local_url
    assert client.get(local_url(asset,int(time.time())-1)).status_code==403
    with db.db() as c:
        assert c.execute("select status from synora.credit_reservations where job_id=%s",(job,)).fetchone()["status"]=="settled"
        record=c.execute("select provenance from synora.assets where id=%s",(asset,)).fetchone()["provenance"]
        assert record["model"]=="procedural-tone" and record["estimated_cost_usd"]==0
    # The same idempotency key is scoped to the second owner.
    other_job=client.post("/v1/music/jobs",json=SPEC,headers=b|{"Idempotency-Key":"api"}).json()["id"]
    assert other_job!=job
    assert client.post(f"/v1/jobs/{other_job}/cancel",headers=b).json()["status"]=="cancelled"

def test_attempt_exhaustion_releases_credit():
    uid=uuid4()
    job=db.submit(uid,"retry",SPEC)
    for attempt in range(1,4):
        row=db.claim()
        assert row["id"]==job["id"] and row["attempts"]==attempt
        db.fail(job["id"],row["lease_token"])
        with db.db() as c:
            c.execute("update synora.jobs set available_at=now() where id=%s",(job["id"],))
    assert db.owned_job(uid,job["id"])["status"]=="failed"
    with db.db() as c:
        assert c.execute("select status from synora.credit_reservations where job_id=%s",(job["id"],)).fetchone()["status"]=="released"

def test_worker_cancel_mid_generation(monkeypatch):
    from synora import worker
    uid=uuid4()
    job=db.submit(uid,"during",SPEC)
    original=worker.FixtureProvider.generate
    def generate(provider,spec,context):
        db.cancel(uid,job["id"])
        return original(provider,spec,context)
    monkeypatch.setattr(worker.FixtureProvider,"generate",generate)
    assert run_one()
    row=db.owned_job(uid,job["id"])
    assert row["status"]=="cancelled" and row["asset_id"] is None
    assert not (settings.media_dir / str(uid) / str(job["id"])).exists()


def test_persistent_library_pagination_and_isolation(monkeypatch):
    uid,other=uuid4(),uuid4()
    token_a,token_b=str(uuid4()),str(uuid4())
    monkeypatch.setattr(api,"settings",replace(settings,fixture_tokens=json.dumps({
        token_a:str(uid),token_b:str(other)}),supabase_url="",supabase_key=""))
    a={"Authorization":f"Bearer {token_a}"}
    b={"Authorization":f"Bearer {token_b}"}
    first=db.submit(uid,"library-a",SPEC)
    assert run_one()
    second=db.submit(uid,"library-b",SPEC|{"prompt":"Second song"})
    db.cancel(uid,second["id"])
    foreign=db.submit(other,"library-other",SPEC|{"prompt":"PRIVATE"})
    db.cancel(other,foreign["id"])
    with TestClient(app) as client:
        endpoint="/v1/music/library"
        assert client.get(endpoint).status_code==401
        assert client.get(endpoint+"?limit=101",headers=a).status_code==422
        page=client.get(endpoint+"?limit=1",headers=a).json()
        assert len(page["items"])==1
        assert page["items"][0]["job"]["id"]==str(second["id"])
        assert page["items"][0]["asset"] is None
        assert page["items"][0]["prompt"]=="Second song"
        assert page["next_cursor"]==str(second["id"])
        page2=client.get(endpoint,params={"cursor":page["next_cursor"]},headers=a).json()
        assert page2["next_cursor"] is None
        assert len(page2["items"])==1
        item=page2["items"][0]
        assert item["job"]["id"]==str(first["id"])
        assert item["asset"]["id"]==item["job"]["asset_id"]
        assert item["asset"]["simulated"] is True
        assert "storage_key" not in item["asset"] and "user_id" not in item["job"]
        assert client.get(item["asset"]["url"]).content[:4]==b"RIFF"
        assert client.get(endpoint,params={"cursor":str(foreign["id"])},headers=a).status_code==422
        assert client.get(endpoint,params={"cursor":str(uuid4())},headers=a).status_code==422
        assert client.get(endpoint,headers=b).json()["items"][0]["prompt"]=="PRIVATE"
        assert client.post(f"/v1/jobs/{first['id']}/cancel",headers=a).json()["status"]=="succeeded"
        assert client.post(f"/v1/jobs/{first['id']}/cancel",headers=b).status_code==404
