"""Explicit fixture-only attempt reconciliation. Never delete uncertain or live assets."""
import argparse
import stat
import time
from uuid import UUID
from . import db
from .config import settings
from .storage import local_path

GRACE_SECONDS = 600

def reconcile_attempt(key: str, min_age_seconds: int = GRACE_SECONDS) -> bool:
    if settings.environment not in ("local", "test") or settings.provider != "fixture":
        raise RuntimeError("cleanup restricted to explicit fixture mode")
    if min_age_seconds < GRACE_SECONDS:
        raise ValueError("cleanup grace cannot be shortened below 600 seconds")
    owner, job, attempt_file = key.split("/")
    if not attempt_file.endswith(".wav"):
        raise ValueError("canonical WAV key required")
    owner_id, job_id, token = UUID(owner), UUID(job), UUID(attempt_file[:-4])
    if key != f"{owner_id}/{job_id}/{token}.wav":
        raise ValueError("canonical WAV key required")
    path = local_path(key)
    root = settings.media_dir.resolve()
    if path.resolve() != root / owner / job / attempt_file or path.is_symlink():
        return False
    cutoff = time.time() - min_age_seconds

    def eligible() -> bool:
        try:
            info = path.lstat()
        except FileNotFoundError:
            return False
        return stat.S_ISREG(info.st_mode) and info.st_mtime <= cutoff

    if not eligible():
        return False
    with db.db() as conn:
        # Same lock ordering as db.complete; publication cannot pass while
        # reconciliation checks the lease and referenced artifact.
        row = conn.execute("""select status,lease_token from synora.jobs
            where id=%s and user_id=%s for update""", (job_id,owner_id)).fetchone()
        if row is None:
            # Unknown/missing jobs need manual investigation.
            return False
        if row["status"] == "running" and row["lease_token"] == token:
            # Even an expired matching token is preserved until recovery fences it.
            return False
        if conn.execute("select 1 from synora.assets where storage_key=%s", (key,)).fetchone():
            return False
        if not eligible() or path.is_symlink():
            return False
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        return True

def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile explicitly identified stale fixture WAVs")
    parser.add_argument("keys", nargs="+")
    args = parser.parse_args()
    if len(args.keys) > 100:
        parser.error("at most 100 keys per invocation")
    deleted = sum(reconcile_attempt(key) for key in args.keys)
    print(f"examined={len(args.keys)} deleted={deleted}")

if __name__ == "__main__":
    main()
