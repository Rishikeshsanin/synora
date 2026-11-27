#!/usr/bin/env bash
set -euo pipefail
test "${GITHUB_ACTIONS:-}" = true
test -f "$1" || { echo "::error::Missing owner-supplied hash lock: $1"; exit 1; }
python3.12 -c 'import sys; assert sys.version_info[:2] == (3, 12)'
python3.12 -m venv "$RUNNER_TEMP/synora-venv"
"$RUNNER_TEMP/synora-venv/bin/python" -m pip install --require-hashes -r "$1"
"$RUNNER_TEMP/synora-venv/bin/python" -m pip check
echo "$RUNNER_TEMP/synora-venv/bin" >> "$GITHUB_PATH"
