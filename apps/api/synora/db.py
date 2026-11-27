import hashlib
import json
from contextlib import contextmanager
from uuid import uuid4
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from .config import settings

class Conflict(Exception): pass
class RateLimited(Exception): pass

@contextmanager
def db():
    with psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=5,
                         options="-c statement_timeout=10000") as conn:
        yield conn

def canonical_hash(spec):
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

def submit(user, key, spec):
    digest = canonical_hash(spec)
    with db() as c:
        # Serializes admissions per owner across API instances.
        c.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", (str(user),))
        old = c.execute("select * from synora.jobs where user_id=%s and idempotency_key=%s", (user,key)).fetchone()
        if old:
            if old["request_hash"] != digest: raise Conflict()
            return old
        counts = c.execute("""select count(*) filter (where created_at > now()-interval '1 minute') as recent,
            count(*) filter (where status in ('queued','running')) as active
            from synora.jobs where user_id=%s""", (user,)).fetchone()
        if counts["recent"] >= 5 or counts["active"] >= 3: raise RateLimited()
        row = c.execute("""insert into synora.jobs(user_id,spec,idempotency_key,request_hash,simulated,provider)
            values(%s,%s,%s,%s,true,'fixture') returning *""", (user,Jsonb(spec),key,digest)).fetchone()
        c.execute("insert into synora.credit_reservations(job_id) values(%s)", (row["id"],))
        return row

def owned_job(user, job):
    with db() as c:
        return c.execute("select * from synora.jobs where id=%s and user_id=%s", (job,user)).fetchone()

def owned_asset(user, asset):
    with db() as c:
        return c.execute("select * from synora.assets where id=%s and user_id=%s", (asset,user)).fetchone()

def cancel(user, job):
    with db() as c:
        row = c.execute("""update synora.jobs set status='cancelled',lease_token=null,lease_until=null,updated_at=now()
            where id=%s and user_id=%s and status in ('queued','running') returning *""", (job,user)).fetchone()
        if row:
            c.execute("update synora.credit_reservations set status='released',updated_at=now() where job_id=%s and status='reserved'", (job,))
            return row
        return c.execute("select * from synora.jobs where id=%s and user_id=%s", (job,user)).fetchone()

def claim():
    with db() as c:
        # Reap expired leases with bounded attempts; settlement is in same transaction.
        dead = c.execute("""update synora.jobs set status='failed',error='{"code":"lease_expired","message":"Generation attempts exhausted"}',
            lease_token=null,lease_until=null,updated_at=now()
            where status='running' and lease_until<=now() and attempts>=3 returning id""").fetchall()
        for row in dead:
            c.execute("update synora.credit_reservations set status='released',updated_at=now() where job_id=%s and status='reserved'", (row["id"],))
        c.execute("""update synora.jobs set status='queued',lease_token=null,lease_until=null,
            available_at=now()+interval '5 seconds',updated_at=now()
            where status='running' and lease_until<=now() and attempts<3""")
        return c.execute("""with next_job as (select id from synora.jobs where status='queued' and available_at<=now()
            and attempts<3 and kind='music' and simulated and provider='fixture'
            order by created_at,id for update skip locked limit 1)
            update synora.jobs j set status='running',attempts=attempts+1,
            lease_token=%s,lease_until=now()+interval '60 seconds',progress=greatest(progress,5),updated_at=now()
            from next_job where j.id=next_job.id returning j.*""", (uuid4(),)).fetchone()

def progress(job, token, value):
    with db() as c:
        return c.execute("""update synora.jobs set progress=greatest(progress,%s),
            lease_until=now()+interval '60 seconds',updated_at=now()
            where id=%s and lease_token=%s and status='running' and lease_until>now()""",
            (min(99,max(0,value)),job,token)).rowcount == 1

def complete(job, token, key, duration, provenance, mime_type='audio/wav'):
    if mime_type != 'audio/wav': raise ValueError('fixture must be WAV')
    with db() as c:
        row = c.execute("""select * from synora.jobs where id=%s and lease_token=%s
            and status='running' and lease_until>now() for update""", (job,token)).fetchone()
        if not row: return False
        asset = c.execute("""insert into synora.assets(user_id,job_id,kind,mime_type,duration_seconds,storage_key,simulated,provenance)
            values(%s,%s,'audio',%s,%s,%s,true,%s) returning id""",
            (row["user_id"],job,mime_type,duration,key,Jsonb(provenance))).fetchone()
        c.execute("""update synora.jobs set status='succeeded',progress=100,asset_id=%s,lease_token=null,
            lease_until=null,error=null,updated_at=now() where id=%s""",(asset["id"],job))
        c.execute("update synora.credit_reservations set status='settled',updated_at=now() where job_id=%s and status='reserved'", (job,))
        return True

def fail(job, token):
    with db() as c:
        row = c.execute("""update synora.jobs set status=case when attempts>=3 then 'failed' else 'queued' end,
            error=case when attempts>=3 then '{"code":"generation_failed","message":"Generation failed"}'::jsonb else null end,
            lease_token=null,lease_until=null,available_at=now()+attempts*interval '5 seconds',updated_at=now()
            where id=%s and lease_token=%s and status='running' and lease_until>now() returning status""",(job,token)).fetchone()
        if row and row["status"]=="failed":
            c.execute("update synora.credit_reservations set status='released',updated_at=now() where job_id=%s and status='reserved'",(job,))
