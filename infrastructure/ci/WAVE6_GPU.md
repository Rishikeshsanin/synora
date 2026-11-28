# Wave 6 optional ACE GPU research host (Agent 5)

Base 242fb312d5cc2a9665e602cb8c94bcedee1d09dd (PR #39, run 46135769287 all 10 jobs green).
Combined Wave 5 is not yet available at branch creation; lead must integrate/rebase against all
six accepted Wave 5 snapshots. This PR does not change Wave 5, application dependencies or provider
activation. No GPU, model weight download, paid services, public notebook service or remote jobs.

## Research-only profile

The pinned source license was read from ACE-Step-1.5 commit ca1e85fe9430179831e6bc6be790c332190a3866:
MIT (Git blob 600451d484a555c1273baa2602f32a37fdd0d0ab). Upstream pyproject pins Linux x86_64
torch 2.10.0+cu128 and includes Gradio 6.2.0, transformer/diffuser ranges, local nano-vllm and
training dependencies. This is a separate dependency surface, **not covered by Synora's green app
audits**. Pinned model card access was unavailable from this session. Prior repository research
reports MIT for the model snapshot; require owner inspection of cached license/card and exact hash,
including model-side code, LM/VAE and any separate weights, before proceeding. MIT is not automatic
commercial clearance or output rights assurance. No fresh upstream vulnerability scan was possible
without that installed environment; the tool verifies supplied audit evidence and refuses missing,
incomplete, mismatched or vulnerable inventories.

The T4 evidence supplied by the owner is distinct from CI: 15/60s instrumentals worked; two FP16
English vocal runs yielded NaNs; FP32 + CPU/DiT offload returned valid 30s audio; Telugu audio failed
semantic vocals/lyrics. Pinned upstream initializer sets CUDA dtype internally (FP16 on pre-Ampere);
do not assume ACESTEP_DTYPE changes it. Agent 3 owns explicit verified precision and inference logic.
Profile minimum GPU total 12 GiB, free 10 GiB, host available 12 GiB are conservative preflight
thresholds, not measured capacity guarantees or hard caps. Owner MX330 is not supported.
Batch 1, at most six cases, 120s per case, four CPU threads, 30-minute session ceiling are
proposed research bounds; benchmark must enforce case/duration limits. Never auto-fallback to
lower precision, CPU synthesis or fixture on numeric failure. No public server or tunnel.

## Owner-run offline preflight

Only a permitted private Linux GPU host or authorized interactive notebook within applicable
free quota; confirm no new spend and use host network isolation independently. The launcher does
not create a network namespace or certify billing. Prepare upstream source and cache manually
using Agent 3's pinned instructions, in a separate Python 3.12 uv environment, not the app venv.
Create a new private workspace outside both repos and cache (mode 0700), no customer data.
```sh
python -m infrastructure.gpu_host --workspace /private/new-session \
  --ace-source /private/ace-pinned \
  --snapshot /private/hf/models--ACE-Step--Ace-Step1.5/snapshots/eb84216a8ece2d56388e401efc28061a0c30a209 \
  --python /private/ace-pinned/.venv/bin/python \
  --authorized-local-gpu --offline-host-confirmed
```
First pass emits only source/license/lock/inventory hashes and writes owner-private inventory.json;
exits 2 pending review. For a second pass place reviewed audit and review JSON in the same private workspace with
mode 0600. An identical private inventory may be reused; changed inventory is rejected and
requires a new review/workspace. The tool requires an editable import from the exact pinned
checkout and its isolated virtual environment (default uv sync behavior), not a similarly named wheel. Never put credentials, raw prompts, user media or environment dumps in CI.

The reviewed pass additionally executes uv --offline pip check --python against the target
virtual environment; this reads installed metadata without syncing or installing packages. Use an independently audited pip-audit environment
to inspect the exact upstream site-packages via --path and --format json; authorize advisory
network access only for this explicit audit phase, before offline inference. Do not install
auditors into the app or change upstream lock silently. Match all installed package names and
versions; review local pinned ace-step/nano-vllm source separately when the auditor cannot resolve
them. No exemptions for vulnerable or skipped registry dependencies. Tool validates coverage
and hashes, not the authenticity/freshness of externally supplied advisory results. Review
package license inventory manually, including UNKNOWN and bundled native libraries. The review
JSON fields: reviewed=true, research_only=true, commercial_release_approved=false,
inventory_sha256, audit_sha256, code_revision, snapshot_revision, source_license_sha256,
upstream_lock_sha256, model_license_document_sha256, package_license_review (all normalized names
mapped to "reviewed-research-only"), reviewed_local_packages (only ace-step/nano-vllm and exact
versions if locally reviewed). No self-generated approval. Add --audit and --review paths on
the second pass. Do not commit this private evidence.

A passing preflight checks local nvidia-smi memory headroom, not torch CUDA or actual model
inference. Agent 3 benchmark must check CUDA, checkpoint content hashes and actual dtype.
Snapshot is not copied or modified. Offline flags and credential allowlist are defense in depth,
not network containment. The private cache/session helper uses an exclusive lock, bounded
process lifetime, process-group teardown and suppressed raw logs; no public arbitrary command
CLI. It is available for the reviewed Agent 3 benchmark integration, not wired to generation
yet. Warm reuse within one handler is Agent 3's responsibility, never retain a service after
session exit. Host-enforced cgroup limits/VRAM and storage quota remain separate owner setup,
and escaped subprocesses require host isolation; never present these soft bounds as hard caps.

CI executes stdlib-only tests of path isolation, audit completeness, inventory consistency,
conservative memory thresholds, pinned editable source import, session exclusivity and
actual disposable child-process timeout/cleanup; no model imports, weights, GPU requests or
upstream network checks. All existing application gates remain unchanged.

First commit 720b046: actual CI 46144273325 foundation 17/17, including four new non-GPU tests and real subprocess timeout. Follow-up adds strict installed source/venv consistency, offline uv dependency consistency check, safe identical inventory reuse and three additional tests. No GPU used.
