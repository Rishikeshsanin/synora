#!/bin/sh
# Only invoked by official Postgres entrypoint in a fresh disposable volume.
set -eu
test "$POSTGRES_DB" = synora_smoke
test "$POSTGRES_USER" = synora_smoke
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /synora-init/auth-bootstrap.sql
for migration in /synora-init/migrations/*.sql; do
  test -f "$migration"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f "$migration"
done
