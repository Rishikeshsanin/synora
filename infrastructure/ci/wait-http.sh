#!/usr/bin/env bash
set -euo pipefail
case "$1" in http://127.0.0.1:*) ;; *) exit 1 ;; esac
for i in {1..60}; do
  if curl --silent --fail --max-time 2 "$1" >/dev/null; then exit 0; fi
  sleep 1
done
echo "::error::Local service did not become ready"
exit 1
