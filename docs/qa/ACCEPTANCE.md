# Independent QA acceptance — Issue #6

Status: **BLOCKED for product release**. Initial base: a4ee580619101461baaa0bffc4ff050eed14ff7b. Main contained only README, AGENTS and architecture/contract/development documents; no application, provider or CI runs at inspection. No defect in unimplemented functionality is claimed. Lead retains release authority.

## Executable suites and evidence

- `tests/integration/test_contract_shapes.py`: independent response validators and synthetic negative fixtures. Local Python 3.13.5 / pytest 9.0.2: 13 passed in 0.13s. Git blob 3fd326165d3180353b8f05af21e932e0fed6212b matches locally tested file. Not product verification; project Python 3.12 remains to be checked.
- `tests/integration/test_live_api.py`: health/readiness, missing authentication, bounds, idempotency-key requirement, four concurrent duplicate requests, owner isolation, completion, simulated provenance and signed local WAV download/decoding. Not run against a service.
- `tests/e2e/test_browser_acceptance.py`: four viewports, basic semantic/keyboard checks, uncaught page errors, existing fixture playback/download and visible simulated disclosure. Not run against a service. Proposed selectors require coordination.
- No paid resource, provider invocation, deployment, production migration, or shared contract change was authorized or performed.

From repository root, use an isolated Python 3.12 environment. Proposed QA dependency versions for reproducibility, subject to devops coordination: pytest==8.3.5, httpx==0.28.1, playwright==1.51.0. Install Chromium with `python -m playwright install chromium`. No root dependency or CI file edits in this PR.

```sh
python -m pytest -q tests/integration/test_contract_shapes.py
# Only after starting an isolated, local fixture-mode API and obtaining two
# distinct test users. Inject tokens privately; never commit or log them.
SYNORA_QA_REQUIRE_LIVE=1 SYNORA_QA_FIXTURE_POSTS=1 python -m pytest -q tests/integration/test_live_api.py
# Only after starting local web app and preparing an existing fixture result.
SYNORA_QA_REQUIRE_BROWSER=1 python -m pytest -q tests/e2e
```

API environment: SYNORA_QA_API_URL (loopback only), SYNORA_QA_TOKEN_A, SYNORA_QA_TOKEN_B; SYNORA_QA_FIXTURE_POSTS=1 explicitly authorizes local fixture-mode POST requests only. Operator must verify the target uses an isolated database and disabled real-provider credentials before enabling POSTs. Browser environment: SYNORA_QA_WEB_URL, SYNORA_QA_FIXTURE_PAGE_URL (existing simulated result), SYNORA_QA_STORAGE_STATE (local authenticated Playwright state; sensitive, keep outside repository). Proposed DOM hooks: generation-provenance, audio-play, audio-download; HTML audio element expected. Coordinate alternatives for Web Audio and non-WAV fixture formats without reducing actual integrity/playback coverage.

Without required configuration live suites skip and are BLOCKED, never PASS for release. Strict flags turn missing config into test failures. CI must report collected, passed, failed and skipped counts separately. Devops owns CI wiring. Do not run generation checks on production or against real providers from these suites.

## Release gates (proposed targets, lead to ratify)

| ID | Acceptance criterion | Evidence / current state |
|---|---|---|
| M1-01 | All documented request/response contracts, UUID and UTC fields, bounds, structured errors; no secret leakage | Fixture validators passed; runtime pending |
| M1-02 | 4 simultaneous equal idempotency requests create exactly 1 job, asset and charge/reservation; changed payload same key rejected; independent accounts isolated | Job identity automated; DB/financial assertion pending |
| M1-03 | Polling exposes status and progress, success has persisted authorized audio, failed job shows error, no silent fallback | Success test authored; failure injection pending |
| M1-04 | Crash worker after claim and after artifact creation; lease expires, recovery completes within lease + polling tolerance, bounded retries and no duplicate settlement | Pending worker, DB and fault hooks |
| M1-05 | Cancel queued/running jobs; cancellation race with success resolves atomically; cancelled jobs cannot be resurrected; release reserved credits | Pending ratified cancel endpoint and worker |
| M1-06 | Two users cannot read/list/update each other's jobs, assets or projects; test RLS with real authenticated principals, no service-role bypass; missing/expired/forged JWT rejected | API read test authored; RLS and remaining endpoints pending |
| M1-07 | Media private; signed URLs expire, tampering fails, unauthorized requests cannot mint URLs; download MIME/signature valid; duration matches decoded media within 0.25s for WAV fixtures; downloaded bytes match expected fixture hash | Local WAV checks authored; expiry, tampering and expected digest pending |
| M1-08 | Browser mobile 320/390, tablet 768, desktop 1440; no horizontal overflow or uncaught JS errors; actual audio advances and download nonempty; keyboard reaches all key controls; screen reader labels, visible focus, contrast WCAG 2.2 AA and reduced motion | Basic Playwright authored; full accessibility and studio journey pending |
| M1-09 | Fixture mode visibly simulated in job, asset and UI; production startup refuses simulated provider; errors do not fall back silently | Runtime checks authored; production config refusal pending |
| M1-10 | On isolated representative deployment, 30 API samples per endpoint, p95 GET <500ms and POST <1s excluding generation; 10 concurrent fixture jobs without unexpected errors; record peak RSS/CPU, queue latency, cold starts and hardware | Proposed budget, no measured product results |
| M1-11 | Real provider authorized; 2 English, 2 Hindi, 2 Telugu vocal prompts and 3 instrumental prompts; decode each, record requested/actual duration, latency, cost, revision, rights, language, quality and provenance; no mocks | Blocked on owner approval and provider access |
| M1-12 | 100% mandatory tests pass on exact integrated commit; no open critical/high release blockers; production smoke on approved deployment; evidence linked | No integrated build yet |
| M2-01 | Reject unsupported signatures, MIME mismatches, truncated/oversized files, traversal filenames; enforce ownership and rights confirmation | Pending upload contract |
| M2-02 | 3–5 distinct concepts tied to audience/brand; no render before explicit approval; revisions invalidate stale approvals | Pending ratified M2 contract |
| M2-03 | Product fidelity: paired source/render comparison, manual review of every logo, packaging text, shape/color; OCR and image similarity assist but never replace human approval; zero fabricated claims or altered logos presented as genuine | Pending assets, storyboard and render engine |
| M2-04 | Export decodes end-to-end, expected aspect ratio/duration, A/V sync within proposed 100ms, no clipping or missing audio, licensed soundtrack reuse | Pending M2 renderer |

### Real music benchmark protocol (not executed)
Only after written budget and provider/license authorization: use fixed original prompts (no impersonation or copyrighted lyrics), capture model revision, capability flags, provider request IDs (redacted), SHA-256 of artifacts, actual cost, wall time, ffprobe output and provenance. Two reviewers score musical coherence, audible artifacts and prompt/language adherence 1–5; proposed minimum median 4 for each dimension with no severe failure. Report individual failures and unsupported controls; never claim exact BPM/lyrics/duration adherence unless demonstrated. A successful fixture run does not satisfy this gate.

### Fault and security protocol
Use isolated test accounts and DB; record job/attempt/reservation counts before and after tests. Inject provider timeout, 429, 5xx, malformed audio, permanent rejection and worker termination; inspect retry bounds, lease fencing, atomic asset publication and no duplicate charges. Test signed URL expiry and changed signature with no token; inspect RLS as both users, not admin. Never log bearer tokens, signed URLs, service-role keys or user media. Reset only dedicated test data. No destructive production testing.

### Contract coordination required
Lead/backend: ratify same-key changed-payload status/code, cancellation endpoint and semantics, retry/fault-injection controls, authenticated test provisioning, fixture WAV format, signed URL TTL and upload API. Frontend: agree stable hooks and an authenticated existing fixture result route. Devops: wire strict suites into isolated fixture CI and publish JUnit/traces with secrets/media excluded. These requests are not unilateral changes to v0.1.

### Defect and evidence template
For each failure: severity (critical: isolation/secret/duplicate charge; high: core workflow broken or fake output presented as real; medium: material usability/performance; low: cosmetic), exact commit and environment, steps, expected vs observed, sanitized logs/artifact IDs, owner and retest result. For each gate: PASS/FAIL/BLOCKED, command, test count, run/job URL, commit, environment and timestamp. Skips are not passes. Keep Issue #6 open until independent integrated and real-provider evidence is obtained.
