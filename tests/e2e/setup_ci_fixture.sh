# Source only in disposable GitHub Actions fixture mode, after web/API/worker startup.
test "${GITHUB_ACTIONS:-}" = true || return 1
test "${SYNORA_ENV:-}" = test || return 1
test "${SYNORA_DISPOSABLE_DB:-}" = 1 || return 1
test "${SYNORA_QA_WEB_URL:-}" = http://127.0.0.1:3000 || return 1
test "${SYNORA_QA_API_URL:-}" = http://127.0.0.1:8000 || return 1
test "${NEXT_PUBLIC_SUPABASE_URL:-}" = http://127.0.0.1:19090 || return 1
(umask 077; exec python "$GITHUB_WORKSPACE/tests/e2e/ci_fixture_auth.py" serve) > "$RUNNER_TEMP/synora-auth-fixture.log" 2>&1 &
fixture_auth_pid=$!
bash "$GITHUB_WORKSPACE/infrastructure/ci/wait-http.sh" http://127.0.0.1:19090/health
kill -0 "$fixture_auth_pid"
export SYNORA_QA_FIXTURE_JOB_ID
SYNORA_QA_FIXTURE_JOB_ID="$(python "$GITHUB_WORKSPACE/tests/e2e/ci_fixture_auth.py" prepare)"
export SYNORA_QA_STORAGE_STATE="$RUNNER_TEMP/synora-browser-a.json"
export SYNORA_QA_STORAGE_STATE_B="$RUNNER_TEMP/synora-browser-b.json"
export SYNORA_QA_FIXTURE_PAGE_URL=http://127.0.0.1:3000/studio
