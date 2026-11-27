# Wave 4 independent QA
Base 2a802b71b36e08684ab6562d21e4f4981984d9b6 (master PR #13, audited PR #28). Master assignment #6 comment 7228020291. Read #29 (execution harness owner Agent 7).
## Actual baseline evidence
CI [46066906111](https://github.com/Rishikeshsanin/synora/actions/runs/46066906111), exact base: 7/10 green. Independently inspected job 140734303175: 4 QA DB passed in 2.63s; job 140734302906: 32 backend passed in 2.72s, Ruff clean, mypy HTTPException.detail incompatible tuple; job 140734303068: 0 npm vulnerabilities, 4 Chromium passed, lint job failed. Job 140734303001: 13 contract passed in 0.02s, 10 live API passed in 1.38s, clean audits, production web build passed; browser 6 passed / 2 failed in 5.24s: missing SYNORA_QA_FIXTURE_PAGE_URL and SYNORA_QA_STORAGE_STATE. These are actual configuration failures, not successful native UI tests. All four previous DB tests (including ambiguity retry) passed; explicit orphan reconciliation coverage absent at baseline. Local git ls-remote actually failed DNS; Python 3.13.5 available, psycopg import fails, Docker and Postgres commands absent. No production resources.
## New mandatory tests
- Extend four-case DB suite: actual aged orphan cleanup after precommit fault, young orphan preservation, committed-file protection, idempotent cleanup; active and expired matching lease protected until recovery fences it; DB-unavailable failure preserves bytes. Explicit fixture-only reconciler from backend, no shortened grace. New separate library test creates 1 A and 2 B jobs, paginates limit=1 including timestamp ties, validates owner-only items, correct asset/provenance, rejects foreign/nonexistent cursor and anonymous access. Total 6 cases, within baseline 5 admissions per identity per minute on fresh isolated DB. Run before competing worker, no production credentials.
- Persisted track gate replaces nonexistent proposed player hooks with native controls, stable per-job library selector and seeded exact job UUID. Two reload cycles, actual WAV decode and digest comparison against server asset, no replacement submission.
- Native test retains two authenticated real API/worker journeys and adds reload, own/foreign library item assertions, logout removal of private track/player. New assertions not yet executed on a combined runtime; no green claim.
## Coordination
#29 comment 7228046447: Agent 7 owns fixture harness; must export SYNORA_QA_FIXTURE_PAGE_URL, SYNORA_QA_FIXTURE_JOB_ID (completed seed for A), SYNORA_QA_STORAGE_STATE and _B, tokens and local API/web URLs. #1 comment 7228046861 requests stable data-testid="library-track-"+job UUID, existing user-visible server fixture label, persistent list. Current base session-only UI does not satisfy persisted gate; do not waive. #5 comment 7228047425: wire exact combined snapshot and preserve no-skips, use fresh DB/dedicated rate budget across suites. QA edits tests only; no auth setup, application, CI or lock changes.
## Commands on combined candidate
```sh
# after disposable DB/bootstrap and fixture env, before competing worker
export SYNORA_QA_DISPOSABLE_DB=1 SYNORA_QA_REQUIRE_DB=1
export PYTHONPATH="$PWD/apps/api:$PWD"
python -m pytest -q -rs tests/integration/test_wave2_worker.py --junitxml="$RUNNER_TEMP/qa-db.xml"
python infrastructure/ci/assert-no-skips.py "$RUNNER_TEMP/qa-db.xml"
# after Agent 7 setup, API/worker and built web, strict env
export SYNORA_QA_REQUIRE_BROWSER=1 SYNORA_QA_REQUIRE_BROWSER_API=1 SYNORA_QA_FIXTURE_POSTS=1
python -m pytest -q -rs tests/e2e --junitxml="$RUNNER_TEMP/browser.xml"
python infrastructure/ci/assert-no-skips.py "$RUNNER_TEMP/browser.xml"
```
Do not expose signed URLs, auth states, tokens, or trace contents. Keep #14 open until new reconciliation tests actually pass on exact combined candidate; keep #29 open until actual native and persisted tests pass. Fixture auth is not real Supabase production JWT acceptance. Release blocked: baseline mandatory lint/type/browser failures, new test execution and real authentication/provider/performance gates outstanding. No merges, paid resources, deployments, Railway or dependency modifications.
