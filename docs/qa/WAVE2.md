# Wave 2 independent evidence (Issue #6)

Baseline integration PR #13, exact SHA 6cc2bc1f314fb80bd9eca39f68e8b7dfc0c01759. Master instructions comment 7227671499 read; docs/INTEGRATION.md read. No main changes, no merges, no real provider calls.

## Observations actually executed

- GitHub Actions run 46064772704 at the baseline: foundation 5 tests passed (job 140727316549); Python job 140727316219 failed at missing requirements-dev.lock; web job 140727316564 failed at missing package-lock.json. API image skipped. No application run evidence.
- Local command `python -m pytest -q tests/integration/test_contract_shapes.py`: 13 passed in 0.04s, Python 3.13.5. Git blob 3fd326165d3180353b8f05af21e932e0fed6212b matches integrated source. This is synthetic contract validation only.
- Issue #14, high: copied exact worker.py blob 021ecb368a6d516d80018adf4001177905efff5b, verified git hash-object. Controlled collaborators: successful claim/progress, temporary on-disk write, db.complete returns False. Executed python repro.py: run_one returned True, unreferenced WAV count 1, expected 0, assertion failed (exit 1). No live database or real provider used in this reproduction. Backend PR #15 at 0e9058d contains a candidate cleanup on definitive False; ambiguous commit errors preserve bytes; retest required.
- Local git ls-remote failed DNS; no Docker, Postgres server, psycopg or Python 3.12. Browser installed but no dependency-built application, no integrated UI execution. Never label unexecuted tests passed.

## New strict executable tests

`tests/integration/test_wave2_worker.py` uses actual bearer auth (no dependency override), two fixture identities, disposable Postgres, real worker, reservation rows, cancellation fencing, expired lease recovery, WAV integrity, signed URL expiry/tamper and byte-identical attachment download. Second case injects cancellation after write before settlement, checks no orphan and released reservation; intentionally fails if defect #14 persists. Expiry clock is injected, not a 300-second real-time wait.

`tests/e2e/test_wave2_browser_api.py` uses Chromium on the actual web origin and actual API/worker through fetch (CORS, two token identities, actual fixture output, playback advancing, media download SHA-256 match). It injects an audio element and download link solely to exercise browser-origin integration; does not prove the application's native player/authenticated Studio flow. Existing Wave 1 browser tests cover the actual local preview, responsive landing, basic keyboard; authenticated Studio still requires frontend fixture login route, state and stable semantic hooks.

Both new files authored, not executed against services. No real Supabase JWT or RLS verification yet. The backend RLS smoke and two real JWT principals must remain separate gates; local fixture bearer auth does not prove Supabase authentication.

## CI coordination with Agent 5

Comment 7227720422 on #5; PR #16 at fe22de6 inspected (strict local Postgres/browser workflow, explicit missing locks/fixture setup). Suggested commands in same checkout (Python 3.12 locked dependencies, FFmpeg, disposable Postgres role/bootstrap and migration, loopback, no paid credentials):

```sh
# Before starting competing worker; fresh DB and unique fixture identities.
export PYTHONPATH="$PWD/apps/api:$PWD"
export SYNORA_QA_DISPOSABLE_DB=1 SYNORA_QA_REQUIRE_DB=1
python -m pytest -q -rs tests/integration/test_wave2_worker.py --junitxml="$RUNNER_TEMP/qa-db.xml"
# Start separate API + worker, set SYNORA_QA_API_URL, SYNORA_QA_WEB_URL and both tokens.
export SYNORA_QA_REQUIRE_LIVE=1 SYNORA_QA_FIXTURE_POSTS=1
python -m pytest -q -rs tests/integration/test_live_api.py --junitxml="$RUNNER_TEMP/live.xml"
# Avoid per-user admission rate by waiting at least 60s or starting a separate fresh DB for next group.
export SYNORA_QA_REQUIRE_BROWSER_API=1
python -m pytest -q -rs tests/e2e/test_wave2_browser_api.py --junitxml="$RUNNER_TEMP/browser-api.xml"
```

Use strict no-skips assertion for each JUnit. Run DB tests separately from app worker, use isolated media folder; API env test/fixture, signing key random, tokens distinct with distinct mapped UUIDs, no production keys. CORS origin equals web origin. No raw tokens, signed URLs, full traces, or media logs published. DB suites have deliberate fault injection only against disposable target. Existing browser suite needs the additional authenticated result setup; do not substitute injected browser elements for a Studio UI pass. CI lockfile and actual app setup owned by Agents 1/2/5. No workflow files changed here.

Release recommendation: BLOCKED. Need integrated exact SHA evidence with zero missing mandatory gates, RLS/real auth, worker recovery and cancellation, security, full native UI, accessibility including contrast/focus/screen reader, performance and authorized real provider benchmark. M2 remains outside M1 release.
