#!/usr/bin/env bash
set -euo pipefail
# GitHub-hosted ephemeral runner only; never attach to an existing instance.
test "${GITHUB_ACTIONS:-}" = true
test -z "$(docker ps -aq --filter name=^/synora-ci-db$)"
docker run -d --name synora-ci-db -e POSTGRES_USER=synora_ci -e POSTGRES_DB=synora_ci -e POSTGRES_PASSWORD=synora-ci-local-only -p 127.0.0.1:55432:5432 postgres:17.6
for i in {1..45}; do
  if docker exec synora-ci-db pg_isready -U synora_ci -d synora_ci >/dev/null; then break; fi
  sleep 1
done
# Confirm TCP readiness, not initdb's temporary Unix socket.
for i in {1..30}; do
  if docker exec synora-ci-db pg_isready -h 127.0.0.1 -U synora_ci -d synora_ci >/dev/null; then break; fi
  sleep 1
done
bash infrastructure/ci/psql.sh < infrastructure/ci/auth-bootstrap.sql
# Apply all migrations in sorted order, with failure on first SQL error.
for migration in supabase/migrations/*.sql; do
  bash infrastructure/ci/psql.sh < "$migration"
done
