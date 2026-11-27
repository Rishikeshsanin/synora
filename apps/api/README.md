# Synora backend (draft)
Python 3.12. API: `uvicorn synora.api:app --port 8000`. Separate worker: `python -m synora.worker`. Run from apps/api. Dockerfile is Render-compatible; no services provisioned. Fixture mode is synthetic WAV, not AI music. Production refuses fixture and no real provider is enabled. Capabilities endpoint exposes unsupported controls.

## Disposable local test
Use a fresh local Supabase instance or PostgreSQL with Supabase-compatible auth roles and auth.uid(); never a shared or live project. Apply the migration only to that disposable database. CLI unavailable in authoring environment, so migration timestamp selected manually; validate with local CLI before integration. Set:
- SYNORA_ENV=test, MUSIC_PROVIDER=fixture, SYNORA_DISPOSABLE_DB=1
- DATABASE_URL pointing at disposable migrated DB
- MEDIA_SIGNING_KEY a randomly generated secret of at least 32 characters
- API_PUBLIC_URL=http://testserver for tests, http://localhost:8000 for manual use
- MEDIA_DIR a private directory shared by local API and worker
- FIXTURE_TOKENS_JSON a JSON mapping of random development bearer tokens to UUIDs; never use in production.
Run `python -m pip install -r requirements-dev.txt` then `python -m pytest -q`. Integration tests expect an otherwise empty disposable database and serial test execution.

For real auth set SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY and use access token verified by Auth /user. Use dedicated Synora-only database login, with only required privileges in synora schema. Storage adapter uses server-only SUPABASE_SERVICE_ROLE_KEY; provision private synora-private bucket only after approval. No bucket created in migration. Local signed URLs expire in five minutes, and download disposition is signed. Never log signed URL query strings: disable proxy and uvicorn access logs for media routes or redact query strings.

## Known limits / gates
- Shared music-engine contract still needs integration with agent #3; adapter currently local protocol and fixture implementation. No inference, cost, or payment requests are made. Zero-unit reservation settled/released transactionally; real balances/provider idempotency require approval and implementation.
- Lease fencing prevents stale workers from publishing, but abandoned attempt files may remain; add safe orphan cleanup after integration. Fixture worker uses local shared filesystem, not Render ephemeral disks; separate production services must use private shared object storage. Real storage adapter not live-verified.
- Project create/list endpoints are proposed extensions; project-to-job association, account deletion lifecycle, list pagination, distributed global request throttling, and production worker heartbeat/real provider are pending. Existing admission limits are per-owner (5/min and 3 active).
- No PostgreSQL, Supabase CLI, Docker or Python 3.12 available in authoring runtime. Full migration/RLS, concurrency, API tests and dependency auditing remain mandatory before merge.
- No root files, other agents' paths or live resources touched.
