import hashlib
import json
from contextlib import contextmanager
from uuid import uuid4
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from .config import settings

class Conflict(Exception):
    pass
class RateLimited(Exception):
    pass

class ProjectNotFound(Exception):
    pass

class ReconciliationRequired(Exception):
    pass

@contextmanager
def db():
    with psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=5,
                         options="-c statement_timeout=10000") as conn:
        yield conn

def canonical_hash(spec):
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

def submit(user, key, spec, project_id=None, experimental_config=None):
    # Preserve legacy idempotency hashes when no project is selected.
    digest = canonical_hash(spec if project_id is None else {
        'spec': spec, 'project_id': str(project_id)})
    if experimental_config is not None:
        digest = canonical_hash({"request_hash":digest,"experimental_config":experimental_config})
    with db() as c:
        # Serializes admissions per owner across API instances.
        c.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", (str(user),))
        if project_id is not None:
            require_project(c, user, project_id)
        old = c.execute("select * from synora.jobs where user_id=%s and idempotency_key=%s", (user,key)).fetchone()
        if old:
            if old["request_hash"] != digest:
                raise Conflict()
            return old
        if experimental_config is not None:
            c.execute("select pg_advisory_xact_lock(72501006)")
            if c.execute("select 1 from synora.jobs where provider='ace-step' and reconciliation_required and status<>'running' limit 1").fetchone():
                raise ReconciliationRequired()
        counts = c.execute("""select count(*) filter (where created_at > now()-interval '1 minute') as recent,
            count(*) filter (where status in ('queued','running')) as active
            from synora.jobs where user_id=%s""", (user,)).fetchone()
        if counts["recent"] >= 5 or counts["active"] >= 3:
            raise RateLimited()
        row = c.execute("""insert into synora.jobs(user_id,spec,idempotency_key,request_hash,simulated,provider,project_id,experimental_config)
            values(%s,%s,%s,%s,%s,%s,%s,%s) returning *""", (user,Jsonb(spec),key,digest,experimental_config is None,
            'fixture' if experimental_config is None else 'ace-step',project_id,
            None if experimental_config is None else Jsonb(experimental_config))).fetchone()
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

def claim(provider="fixture"):
    if provider not in ("fixture","ace-step"):
        raise ValueError("unsupported claim provider")
    with db() as c:
        if provider=="ace-step":
            c.execute("select pg_advisory_xact_lock(72501006)")
            expired=c.execute("""update synora.jobs set status='failed',
                error='{"code":"provider_reconciliation_required","message":"Experimental generation needs operator reconciliation"}',
                lease_token=null,lease_until=null,updated_at=now()
                where provider='ace-step' and status='running' and lease_until<=now() returning id""").fetchall()
            for row in expired:
                c.execute("update synora.credit_reservations set status='released',updated_at=now() where job_id=%s and status='reserved'",(row["id"],))
            if c.execute("select 1 from synora.jobs where provider='ace-step' and reconciliation_required limit 1").fetchone():
                return None
            return c.execute("""with next_job as (select id from synora.jobs
                where status='queued' and provider='ace-step' and not simulated and attempts=0
                and experimental_config is not null and kind='music' and available_at<=now()
                order by created_at,id for update skip locked limit 1)
                update synora.jobs j set status='running',attempts=1,reconciliation_required=true,
                lease_token=%s,lease_until=now()+interval '60 seconds',progress=5,updated_at=now()
                from next_job where j.id=next_job.id returning j.*""",(uuid4(),)).fetchone()
        # Reap expired leases with bounded attempts; settlement is in same transaction.
        dead = c.execute("""update synora.jobs set status='failed',error='{"code":"lease_expired","message":"Generation attempts exhausted"}',
            lease_token=null,lease_until=null,updated_at=now()
            where provider='fixture' and simulated and status='running' and lease_until<=now() and attempts>=3 returning id""").fetchall()
        for row in dead:
            c.execute("update synora.credit_reservations set status='released',updated_at=now() where job_id=%s and status='reserved'", (row["id"],))
        c.execute("""update synora.jobs set status='queued',lease_token=null,lease_until=null,
            available_at=now()+interval '5 seconds',updated_at=now()
            where provider='fixture' and simulated and status='running' and lease_until<=now() and attempts<3""")
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
    if mime_type != 'audio/wav':
        raise ValueError('fixture must be WAV')
    with db() as c:
        row = c.execute("""select * from synora.jobs where id=%s and lease_token=%s
            and status='running' and lease_until>now() for update""", (job,token)).fetchone()
        if not row:
            return False
        if row["provider"]=="ace-step" and (provenance.get("simulated") is not False
                or provenance.get("storage_backend")!="local-ace" or not row["upstream_job_id"]):
            raise ValueError("local ACE publication requires fenced provenance")
        asset = c.execute("""insert into synora.assets(user_id,job_id,kind,mime_type,duration_seconds,storage_key,simulated,provenance)
            values(%s,%s,'audio',%s,%s,%s,%s,%s) returning id""",
            (row["user_id"],job,mime_type,duration,key,row["simulated"],Jsonb(provenance))).fetchone()
        c.execute("""update synora.jobs set status='succeeded',progress=100,asset_id=%s,lease_token=null,
            lease_until=null,error=null,reconciliation_required=false,updated_at=now() where id=%s""",(asset["id"],job))
        c.execute("update synora.credit_reservations set status='settled',updated_at=now() where job_id=%s and status='reserved'", (job,))
        return True

def fail(job, token):
    with db() as c:
        row = c.execute("""update synora.jobs set status=case when provider='ace-step' or attempts>=3 then 'failed' else 'queued' end,
            error=case when provider='ace-step' then '{"code":"provider_reconciliation_required","message":"Experimental generation needs operator reconciliation"}'::jsonb
            when attempts>=3 then '{"code":"generation_failed","message":"Generation failed"}'::jsonb else null end,
            lease_token=null,lease_until=null,available_at=now()+attempts*interval '5 seconds',updated_at=now()
            where id=%s and lease_token=%s and status='running' and lease_until>now() returning status""",(job,token)).fetchone()
        if row and row["status"]=="failed":
            c.execute("update synora.credit_reservations set status='released',updated_at=now() where job_id=%s and status='reserved'",(job,))


def music_library(owner, limit, cursor=None, include_simulated=True, project_id=None):
    """Keyset pagination; cursor must identify a visible job belonging to owner."""
    with db() as c:
        if project_id is not None:
            require_project(c, owner, project_id)
        marker = None
        if cursor is not None:
            marker = c.execute("""select created_at,id from synora.jobs
                where user_id=%s and id=%s and kind='music' and (%s or (not simulated and experimental_config is null))
                and (%s::uuid is null or project_id=%s)""",
                (owner,cursor,include_simulated,project_id,project_id)).fetchone()
            if marker is None:
                raise ValueError("invalid library cursor")
        query = """select j.*, jsonb_build_object(
            'id',a.id,'kind',a.kind,'mime_type',a.mime_type,
            'duration_seconds',a.duration_seconds,'storage_key',a.storage_key,
            'simulated',a.simulated,'provenance',a.provenance) as joined_asset
            from synora.jobs j left join synora.assets a
            on a.id=j.asset_id and a.user_id=j.user_id and a.job_id=j.id
            where j.user_id=%s and j.kind='music' and (%s or (not j.simulated and j.experimental_config is null))
            and (%s::uuid is null or j.project_id=%s)"""
        if marker is not None:
            return c.execute(query+""" and (j.created_at,j.id)<(%s,%s)
                order by j.created_at desc,j.id desc limit %s""",
                (owner,include_simulated,project_id,project_id,marker["created_at"],marker["id"],limit+1)).fetchall()
        return c.execute(query+" order by j.created_at desc,j.id desc limit %s",
                         (owner,include_simulated,project_id,project_id,limit+1)).fetchall()


def require_project(conn, owner, project_id):
    """Never distinguish another owner's project from an absent project."""
    row = conn.execute("""select id,name,created_at from synora.projects
        where id=%s and user_id=%s""", (project_id,owner)).fetchone()
    if row is None:
        raise ProjectNotFound()
    return row


def owned_project(owner, project_id):
    with db() as conn:
        return require_project(conn, owner, project_id)


def record_upstream(job, token, upstream_id):
    if not isinstance(upstream_id,str) or not 1<=len(upstream_id)<=128 or not upstream_id.isascii() or not upstream_id.isprintable():
        raise ValueError("invalid upstream job identifier")
    with db() as c:
        return c.execute("""update synora.jobs set upstream_job_id=%s,updated_at=now()
            where id=%s and lease_token=%s and status='running' and lease_until>now()
            and provider='ace-step' and upstream_job_id is null""",(upstream_id,job,token)).rowcount==1
