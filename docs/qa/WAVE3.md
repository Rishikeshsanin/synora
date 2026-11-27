# Wave 3 independent QA — Issue #6

## Exact evidence
Master base 457c5fa4d0536e28dcb4274cc6960834dbeb8bb0, PR #13. Read master comments 7227812981 and 7227859406, and Agent 7 coordination 7227864844. PR #21 head 987e552b637465b89529cd5ccaf876f42ea6262e, workflow [46066021523](https://github.com/Rishikeshsanin/synora/actions/runs/46066021523). Inspected logs, not merely workflow colors:
- qa-db job 140731494668: 2 passed in 1.70s, including original two-bearer recovery/security and definite rejected settlement cleanup. Strict audit FAILED (7 Starlette vulnerabilities).
- backend job 140731494797: 30 passed in 2.86s; audit, Ruff and mypy FAILED.
- integrated job 140731494976: 13 contract tests passed in 0.02s; 10 live API tests passed in 1.87s; strict runtime audit FAILED; Next build FAILED with SupabaseClient generic mismatch; no browser acceptance evidence.
- RLS smoke job 140731494451 and API image job 140731494766 succeeded.
- Earlier PR #21 candidate c095af67968c40dc7a4b8a7c06938ce88974c271, run 46065899924 job 140731006045: 2 DB tests passed in 1.33s, audit failed. Master run 46065771578 blocked QA tests at dependency audit. Do not transfer test counts across commits.
- Direct local git ls-remote returned DNS failure. Python 3.13.5 and Node/FFmpeg available; Python 3.12, Postgres and Docker absent. New tests authored but not locally executed against services.

## Changes
- Extend existing strict disposable PostgreSQL tests with lost commit acknowledgement after real DB commit (keep committed audio, single settlement, private access) and precommit disconnect (retry, exactly one authoritative asset/settlement, report retained abandoned bytes). No production DB or real provider. The second case intentionally does not demand immediate deletion before safe reconciliation; issue #14 remains open until actual bounded orphan reconciliation and retest are verified. Faults are controlled injections, not real network outages.
- Correct stale local-preview text assertion to exact integrated local-fixture disclosure and separately assert simulated-development notice. No weaker provenance gate.
- Native Studio test uses actual page, two separate pre-authenticated storage states supplied by execution harness, actual generation POST with expected bearer, provider fixture, actual app audio, download, digest equality to signed server artifact, cross-owner denial, signout clearing playback, 390px viewport and reduced-motion preference. No API interception, injected audio elements, or auth bypass. This is still fixture auth, not proof of real Supabase JWTs. Existing persisted-track and browser-origin gates retained.
- Agent 7 owns execution harness/fixture setup; Agent 1 owns product UI/library; Agent 2 owns storage reconciliation; Agent 5 owns workflows and locks. Comments on #2, #5, #6 coordinate responsibilities. No overlapping implementation or lock edits.

## Execution commands
Run on exact combined candidate after patched dependencies, in isolated CI. Existing strict QA env and no-skips gate still apply. Before competing worker startup:
```sh
export SYNORA_QA_REQUIRE_DB=1 SYNORA_QA_DISPOSABLE_DB=1
export PYTHONPATH="$PWD/apps/api:$PWD"
python -m pytest -q -rs tests/integration/test_wave2_worker.py --junitxml="$RUNNER_TEMP/qa-db.xml"
python infrastructure/ci/assert-no-skips.py "$RUNNER_TEMP/qa-db.xml"
```
Native test requires local API/worker/web and two authenticated fixture storage states, SYNORA_QA_STORAGE_STATE and SYNORA_QA_STORAGE_STATE_B. Set SYNORA_QA_REQUIRE_BROWSER=1, SYNORA_QA_FIXTURE_POSTS=1, SYNORA_QA_API_URL, SYNORA_QA_WEB_URL, SYNORA_QA_TOKEN_A/B; use dedicated identities or wait past rate-limit window before running. Agent 7 provisions storage states, never commit tokens or report signed URLs. No mocked generation. Use existing strict browser CI including persisted-track test (do not skip it).
```sh
python -m pytest -q -rs tests/e2e/test_wave3_native_studio.py --junitxml="$RUNNER_TEMP/native.xml"
python infrastructure/ci/assert-no-skips.py "$RUNNER_TEMP/native.xml"
```
## Release verdict
BLOCKED: seven Starlette advisories, frontend audit/build/lint/type failures, other mandatory CI failures; native authenticated and persisted Studio, actual latest candidate execution, ambiguous orphan reconciliation, real Supabase auth/RLS with two genuine users (fixture identities and transactional smoke are not equivalent), full a11y/performance and authorized actual AI provider still unverified. Definitive rejection regression passed on #21, not a reason to close #14. No merges, paid resources, Railway or deployment.
