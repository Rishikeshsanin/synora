#!/usr/bin/env bash
set -euo pipefail
test "${GITHUB_ACTIONS:-}" = true
exec docker exec -i synora-ci-db psql -X -v ON_ERROR_STOP=1 -U synora_ci -d synora_qa
