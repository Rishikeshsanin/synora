# Source from a disposable GitHub-hosted runner. Values are synthetic test-only.
test "${GITHUB_ACTIONS:-}" = true || return 1
export SYNORA_ENV=test MUSIC_PROVIDER=fixture SYNORA_DISPOSABLE_DB=1
export DATABASE_URL=postgresql://synora_ci:synora-ci-local-only@127.0.0.1:55432/synora_qa
export MEDIA_DIR="$RUNNER_TEMP/synora-media" API_PUBLIC_URL=http://127.0.0.1:8000
mkdir -p "$MEDIA_DIR"
chmod 700 "$MEDIA_DIR"
export CORS_ORIGINS=http://127.0.0.1:3000
export SYNORA_REAL_GENERATION_ENABLED=false SYNORA_REAL_MUSIC_APPROVED=0
# Store ephemeral test credentials outside the repository, with restricted permissions.
if [ ! -f "$RUNNER_TEMP/synora-fixture.env" ]; then
  (umask 077; python3.12 - <<'PY' > "$RUNNER_TEMP/synora-fixture.env"
import json, secrets, shlex
a, b = secrets.token_hex(24), secrets.token_hex(24)
key = secrets.token_hex(32)
tokens = {a:"11111111-1111-4111-8111-111111111111",b:"22222222-2222-4222-8222-222222222222"}
for name, value in {"MEDIA_SIGNING_KEY":key,"SYNORA_QA_TOKEN_A":a,"SYNORA_QA_TOKEN_B":b,"FIXTURE_TOKENS_JSON":json.dumps(tokens)}.items():
    print("export " + name + "=" + shlex.quote(value))
PY
  )
fi
source "$RUNNER_TEMP/synora-fixture.env"
printf '::add-mask::%s\n' "$MEDIA_SIGNING_KEY" "$SYNORA_QA_TOKEN_A" "$SYNORA_QA_TOKEN_B" "$FIXTURE_TOKENS_JSON"
