#!/usr/bin/env bash
# Only a disposable GitHub-hosted runner. No provider secrets or remote services.
set -euo pipefail
test "${GITHUB_ACTIONS:-}" = true
test "${RUNNER_OS:-}" = Linux
source infrastructure/ci/fixture-env.sh
# Shared storage is owned by the canonical image's non-root UID.
# Only this newly created runner-temp media directory is touched.
test "$MEDIA_DIR" = "$RUNNER_TEMP/synora-media"
sudo chown 10001:10001 "$MEDIA_DIR"
sudo chmod 700 "$MEDIA_DIR"
export MEDIA_DIR=/media
export SYNORA_QA_REQUIRE_LIVE=1 SYNORA_QA_FIXTURE_POSTS=1
export SYNORA_QA_API_URL="$API_PUBLIC_URL"
# --network host lets containers reach the disposable loopback Postgres.
# Explicit environment allowlist: no inherited cloud/provider credentials.
args=(--network host --user 10001:10001 --cap-drop ALL --security-opt no-new-privileges
  --mount "type=bind,src=$RUNNER_TEMP/synora-media,dst=/media"
  -e SYNORA_ENV -e MUSIC_PROVIDER -e DATABASE_URL -e MEDIA_DIR
  -e MEDIA_SIGNING_KEY -e API_PUBLIC_URL -e CORS_ORIGINS -e FIXTURE_TOKENS_JSON
  -e SYNORA_REAL_GENERATION_ENABLED -e SYNORA_REAL_MUSIC_APPROVED)
docker run -d --name synora-ci-fixture-api "${args[@]}" synora-api:ci uvicorn synora.api:app --host 127.0.0.1 --port 8000 --no-access-log
docker run -d --name synora-ci-fixture-worker "${args[@]}" synora-api:ci python -m synora.worker
bash infrastructure/ci/wait-http.sh "$API_PUBLIC_URL/ready"
python -m pytest -q -rs tests/integration/test_live_api.py --junitxml="$RUNNER_TEMP/container-live.xml"
python infrastructure/ci/assert-no-skips.py "$RUNNER_TEMP/container-live.xml"
test "$(docker inspect -f '{{.State.Running}}' synora-ci-fixture-worker)" = true
