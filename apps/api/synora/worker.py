import logging
import time
from .config import settings
from . import db
from .models import MusicSpec
from .provider import FixtureProvider
from .storage import put_local

log=logging.getLogger("synora.worker")
class LostLease(Exception): pass

def run_one():
    if settings.provider != "fixture": return False
    row=db.claim()
    if not row: return False
    job, token=row["id"],row["lease_token"]
    def update(value):
        if not db.progress(job,token,value): raise LostLease()
    try:
        result=FixtureProvider().generate(MusicSpec.model_validate(row["spec"]),update)
        update(90)
        key=f'{row["user_id"]}/{job}/{token}.wav'
        put_local(key,result.data)
        db.complete(job,token,key,result.duration_seconds,result.provenance)
    except LostLease:
        log.info("lease_lost job=%s",job)
    except Exception:
        log.warning("generation_attempt_failed job=%s",job)
        db.fail(job,token)
    return True

def main():
    logging.basicConfig(level=logging.INFO)
    if settings.provider != "fixture":
        raise SystemExit("No approved active provider")
    while True:
        try:
            if not run_one(): time.sleep(1)
        except Exception:
            log.warning("worker_database_unavailable")
            time.sleep(5)

if __name__=="__main__": main()
