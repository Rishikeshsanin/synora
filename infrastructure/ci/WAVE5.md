# Wave 5 — disposable CPU development smoke

Baseline 439327e8d4ad2910b349cf5e74bbd53e1aeed92a; all ten jobs passed in 46068373250.
The original postgres-only Compose file and existing CI container/browser acceptance remain unchanged.
This separate stack validates the packaged API and worker on CPU using the actual local database
and original synthetic fixture provider. It does NOT generate AI music, run real Supabase auth,
or start a frontend; existing CI native browser tests still cover the fixture UI.

## Local use (Windows Docker Desktop Linux containers / Linux)
Select a local Docker context (no DOCKER_HOST/DOCKER_CONTEXT override). Use Python 3.12,
the existing audited QA lock, and an isolated virtual environment outside the repo. From repo root:
```sh
python -m pip install --require-hashes -r infrastructure/ci/pip.lock
python -m pip install --require-hashes -r tests/requirements-dev.lock
python -m pip check
python infrastructure/local_smoke.py --confirm-disposable
```
The command builds the canonical image (public dependency downloads may be necessary), starts
a random disposable Compose project, applies the auth SQL shim and all migrations to a fresh
database, runs the existing 10-case strict live API suite, verifies actual container security
and resource settings, and removes its project, volumes and unique image tag. Use --port 18082
if 18081 is occupied. No global prune, existing volume reuse, host DB exposure, GPU requests,
real provider credentials or remote Docker context. No secrets are printed or saved by the launcher;
local daemon administrators can inspect container environment. Test credentials are ephemeral
and synthetic. No source data, real accounts or user uploads should enter this stack.
If interrupted during forced termination, inspect ONLY the exact printed project name and
clean up its resources; never prune unrelated Docker resources. The project is a smoke tool, not
a durable local workspace or staging deployment.

Resource envelope: database 512 MiB/1 CPU, API 512 MiB/1 CPU, worker 768 MiB/1.5 CPUs,
128 processes each; shared named private media volume, API/worker non-root read-only rootfs,
bounded /tmp. Actual CPU/RAM consumption is not benchmarked by these caps; no GPU is required.
Build memory is not constrained by these runtime limits. MX330 2 GB VRAM is not used.
Existing green locks unchanged. No release approval or cloud activation.
