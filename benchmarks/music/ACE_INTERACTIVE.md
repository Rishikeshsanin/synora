# Single genuine ACE-Step experiment — owner-operated, not executed in Wave 3

This is a bounded local-process research path for a permitted personal/university GPU or temporary interactive notebook (only within its applicable free quota and terms). No HTTP server/tunnel, public deployment, paid API, GPU rental or automated notebook scheduling. Never use customer data or copyrighted reference material. Stop before any paid or quota-overage prompt. Local script cannot prove a host's billing or network isolation; operator must confirm both. Use fresh private workspace, allow at least ~25–35 GB free disk plus dependency space and compatible NVIDIA CUDA 12.8 driver; 24 GB VRAM preferred, smaller cards not guaranteed. Do not claim the model has run until actual artifact and telemetry exist.

## Prepare (manual, authorized downloads only)

Use Python 3.12, Git, uv, FFmpeg and a compatible GPU. In a permitted environment:

```bash
git clone https://github.com/ace-step/ACE-Step-1.5.git ace-pinned
git -C ace-pinned checkout --detach ca1e85fe9430179831e6bc6be790c332190a3866
cd ace-pinned
uv sync --locked --python 3.12
uv run --locked python -c 'from huggingface_hub import snapshot_download; print(snapshot_download(repo_id="ACE-Step/Ace-Step1.5", revision="eb84216a8ece2d56388e401efc28061a0c30a209"))'
cd ..
```

Record returned cache snapshot absolute path (must end in snapshots/eb84216a8ece2d56388e401efc28061a0c30a209). Confirm no charged downloads or hosting, inspect upstream lock and model/checkpoint licenses; snapshot path alone is not a cryptographic attestation. The experiment records weight SHA-256 values for later independent comparison. Do not modify upstream checkpoint cache. Disconnect network or use host-supported no-network execution after downloads; offline environment flags alone are not a complete network sandbox.

## Run a single 15-second instrumental

From Synora repository root (set actual absolute paths):

```bash
PYTHONPATH="$PWD" /absolute/path/ace-pinned/.venv/bin/python -m benchmarks.music.ace_interactive \
  --ace-source /absolute/path/ace-pinned \
  --snapshot /absolute/path/models--ACE-Step--Ace-Step1.5/snapshots/eb84216a8ece2d56388e401efc28061a0c30a209 \
  --output /private/new-ace-experiment \
  --authorized-local-gpu
```

The source pin, clean tracked tree, snapshot path, required checkpoints, CUDA and disk are checked before loading. The snapshot is copied into the private output directory because upstream may synchronize model-side code. The first experiment uses the official DiT generation API with no LM, batch one, eight steps, original prompt, no mastering/normalization, seed 42, 15-second target. No external services or remote retries. Stop if it fails; do not silently fall back to fixture, unpinned models, CPU or paid hosting.

Inspect experiment.json, audio SHA-256, actual duration, cold initialization, generation wall time, PyTorch allocated/reserved memory, GPU identity and listen to the artifact. Peak memory measures PyTorch allocator, not total device/host use. The script does not certify actual cost, quality or reproducibility. Only after this manual gate, extend to multilingual lyrics and the nine-case benchmark (separate LM verification required). Script has not executed actual ACE-Step weights in this session.

Pinned upstream references:
- [Official Python inference](https://github.com/ace-step/ACE-Step-1.5/blob/ca1e85fe9430179831e6bc6be790c332190a3866/docs/en/INFERENCE.md)
- [Initialization signature](https://github.com/ace-step/ACE-Step-1.5/blob/ca1e85fe9430179831e6bc6be790c332190a3866/acestep/core/generation/handler/init_service_orchestrator.py)
- [Checkpoint checks](https://github.com/ace-step/ACE-Step-1.5/blob/ca1e85fe9430179831e6bc6be790c332190a3866/acestep/model_downloader.py)
- [Pinned model snapshot](https://huggingface.co/ACE-Step/Ace-Step1.5/tree/eb84216a8ece2d56388e401efc28061a0c30a209)

See Wave 2 provider/hosting license research. All hosted generation remains disabled in production.
