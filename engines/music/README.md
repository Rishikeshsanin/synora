# Synora music engine (Issue #3)

This package implements the lead-owned v0.1 Python provider contract. It does not change shared schemas, charge users, deploy services, or handle storage/database authorization. Python 3.12 + FFmpeg/ffprobe are required; no third-party Python dependency for the base adapters.

```python
from pathlib import Path
from engines.music import MusicSpec, GenerationContext, registry
provider = registry()["fixture"]
output = provider.generate(MusicSpec(prompt="Bright original piano cue"),
                           GenerationContext(Path("/private/new-job-dir")))
assert output.simulated
```

Worker must use a private unique directory per attempt, preserve the returned MIME/duration/provenance, persist upstream ID in the context callback, and upload the validated artifact before marking success. Never send upstream URLs to users. Context progress is coarse (fixture per second, real adapter lifecycle only), not provider percent. Cancellation is local; upstream work may finish and cost money. Remote timeouts/ambiguous submissions require reconciliation before resubmission; do not automatically retry a paid generation. No automatic fallback to fixture. Registry defaults to fixture in dev; production excludes fixture and context independently rejects it. Server environment must explicitly set production. User input must never control provider URL, credential or approval.

## Configuration

- All real providers: SYNORA_REAL_MUSIC_APPROVED=1, server-created GenerationContext(allow_real=True,budget_usd=reserved_amount). These flags are operator-only and not substitutes for billing or owner approval.
- ACE: SYNORA_ACE_APPROVED=1, SYNORA_ACE_URL (trusted private HTTPS origin or localhost HTTP), SYNORA_ACE_KEY, SYNORA_ACE_MAX_COST_USD (positive conservative per-request reservation), SYNORA_ACE_WEIGHTS_REVISION=eb84216a8ece2d56388e401efc28061a0c30a209, SYNORA_ACE_CODE_REVISION=ca1e85fe9430179831e6bc6be790c332190a3866. Configure server with pinned weights and code; attestation is configuration, not remote cryptographic proof. Inspect upstream code/LM/VAE dependency revisions and verify deployed weights before approval. Use a private network and no public upstream audio route.
- Lyria: SYNORA_LYRIA_APPROVED=1, GEMINI_API_KEY, SYNORA_LYRIA_MODEL=lyria-3.5 or lyria-3-clip-preview. Model revision is API revision, not a fixed checkpoint. The quoted list price is not billing telemetry. Verify account terms, region, model access, price and current quotas first.

Capabilities specify targets vs prompts vs fixed duration. Telugu support is an experiment, not a certified capability. Fixture accepts all specs only to exercise plumbing and generates a procedural tone; no vocals, genre fidelity, or musical generation. It is never a customer deliverable. Real adapters are runnable against documented API formats but have not been called against actual providers.

Audio validation probes format, decodes full audio, rejects invalid/silent/oversize files and extracts duration, channels, codec, sample rate, SHA256 and basic peak/RMS. FFmpeg must run in a restricted worker container (resource/cpu/memory limits, private files, no network). Optional master() targets -16 LUFS, -1.5 dBTP, 11 LRA with FFmpeg; verify measured loudness in future, no claim of professional mastering. Preserve original and watermark; do not process providers whose terms prohibit transformation. AI stem separation, remix and continuation are not enabled; see PROVIDERS.md.

Run tests: python -m unittest discover -s engines/music/tests -v. Benchmark: python -m benchmarks.music.run --output /tmp/new-run. Do not write private media or credentials into Git. No root dependency or workflow changes in this branch. Integrator/DevOps should add the test command to existing smoke CI.
