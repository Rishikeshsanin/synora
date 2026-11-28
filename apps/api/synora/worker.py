import logging
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from .config import settings
from . import db, local_ace
from .models import MusicSpec
from .provider import to_engine_spec, validate_fixture
from engines.music.core import GenerationContext
from engines.music.providers import FixtureProvider
from .storage import put_local, delete_local

log=logging.getLogger("synora.worker")
class LostLease(Exception):
    pass

def run_one():
    if settings.provider not in ("fixture","ace-step") or settings.environment == "production":
        return False
    real=settings.provider=="ace-step"
    row=db.claim("ace-step") if real else db.claim()
    if not row:
        return False
    job, token=row["id"],row["lease_token"]
    key=f'{row["user_id"]}/{job}/{token}.wav'
    last_check=0.0
    lost=False
    def update(value):
        nonlocal lost,last_check
        if not db.progress(job,token, min(89, int(value*0.89))):
            lost=True
            raise LostLease()
        last_check=time.monotonic()
    def cancelled():
        nonlocal lost,last_check
        if lost:
            return True
        if time.monotonic()-last_check >= 1:
            if not db.progress(job,token,0):
                lost=True
            last_check=time.monotonic()
        return lost
    try:
        public_spec=MusicSpec.model_validate(row["spec"])
        spec=to_engine_spec(public_spec)
        with TemporaryDirectory(prefix="synora-attempt-") as tmp:
            directory=Path(tmp)
            if real:
                local_ace.validate_request(public_spec)
                if row["experimental_config"]!=local_ace.options(settings):
                    raise ValueError("local ACE configuration changed")
                def upstream(upstream_id):
                    if not db.record_upstream(job,token,upstream_id):
                        raise LostLease()
                ctx=local_ace.LocalAceContext(output_dir=directory,seed=42,timeout_seconds=900,
                    cancelled=cancelled,progress=update,allow_real=True,budget_usd=0,
                    production=False,upstream_job=upstream,config=settings)
                output=local_ace.provider(settings,ctx).generate(spec,ctx)
                data,duration,provenance=local_ace.validate_output(output,directory,public_spec,settings)
            else:
                ctx=GenerationContext(output_dir=directory,seed=42,timeout_seconds=180,
                                      cancelled=cancelled,progress=update,allow_real=False,
                                      budget_usd=0,production=False)
                output=FixtureProvider().generate(spec,ctx)
                data,duration,provenance=validate_fixture(output,directory,spec.duration_seconds)
            if not db.progress(job,token,90):
                raise LostLease()
            put_local(key,data)
            # A definite stale result can be removed. An exception may mean the
            # commit succeeded but its acknowledgement was lost: preserve bytes.
            if not db.complete(job,token,key,duration,provenance,output.mime_type):
                delete_local(key)
    except LostLease:
        log.info("lease_lost job=%s",job)
    except Exception:
        if not lost:
            log.warning("generation_attempt_failed job=%s",job)
            db.fail(job,token)
    return True

def main():
    logging.basicConfig(level=logging.INFO)
    if settings.provider not in ("fixture","ace-step") or settings.environment == "production":
        raise SystemExit("No approved active provider")
    while True:
        try:
            if not run_one():
                time.sleep(1)
        except Exception:
            log.warning("worker_database_unavailable")
            time.sleep(5)

if __name__=="__main__":
    main()
