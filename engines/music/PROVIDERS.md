# Provider research / activation gates — 2026-11-28

| Model | Controls and suitability | Rights / cost / status |
|---|---|---|
| ACE-Step 1.5 turbo | Explicit duration 10–600s and BPM 30–300 in upstream API; Synora limits 15–120s and 40–200. Text, lyrics, language, style, seed, 8-step turbo. LM description mode for prompt-only vocals. | Official code MIT, model repository MIT at pinned revision; self-host candidate. GPU and dependencies cost separately. MIT does not guarantee output exclusivity or absence of third-party rights. No production activation. |
| ACE-Step 1.5 XL turbo / XL base | Official 4B DiT XL variants; quality vs speed to be measured. Base may support additional editing; not interchangeable automatically. | Candidate only: verify individual checkpoint revisions/licenses and hardware before use. |
| Google Lyria 3.5 / Lyria 3 Clip | Official Gemini Interactions REST API revision 2026-05-20. Full song prompt-based length, fixed 30s clip, vocals/instrumentals, lyric conditioning; no deterministic seed; SynthID. | $0.08/song / $0.04/clip published price; paid, no free tier indicated. Commercial SaaS terms/account approval pending; no invocation. |
| Eleven Music music_v2_5 | Official compose endpoint, lyrics and section-level editing. | Model resale including multi-model offering requires explicit written authorization (Music Terms 4.3); pure-play terms also require review. No adapter or activation. Plan-based costs; request a written SaaS quote. |
| Meta MusicGen | Instrumental candidate only. | Code MIT, weights CC-BY-NC 4.0: exclude from commercial product. |
| Stable Audio Open 1.0 | Short instrumental/audio textures, not primary lyrics-to-song model. | Community license; verify revenue thresholds, usage restrictions and model weights separately. Exclude until cleared. |

## ACE deployment evidence

- Official source pinned: https://github.com/ace-step/ACE-Step-1.5/commit/ca1e85fe9430179831e6bc6be790c332190a3866 ; latest release endpoint returned v0.1.8 when inspected (release: https://github.com/ace-step/ACE-Step-1.5/releases/tag/v0.1.8). Code pin is main commit, not a claim that this is that tag.
- Model: https://huggingface.co/ACE-Step/Ace-Step1.5/tree/eb84216a8ece2d56388e401efc28061a0c30a209/acestep-v15-turbo (MIT, decoder folder 4.79 GB). Pin entire snapshot; lock any separate LM, VAE, code and environment dependencies before production.
- https://ace-step.github.io/ACE-Step-1.5/en/API documents release_task, query_result, audio, model inventory, seed and batch. https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/INFERENCE.md describes instrumental lyric marker. https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/GRADIO_GUIDE.md describes hardware-dependent LM selection.
- Vendor reports consumer GPU support starting around 4 GB VRAM; not a guarantee for full LM, 120s, or XL. Start test on 24 GB CUDA GPU (e.g. RTX 4090/L4), batch 1; measure memory and latency. XL and larger LM require separate capacity tests. No vendor speed number is treated as measured Synora result. Pinned code constants explicitly list en, hi and te: https://github.com/ace-step/ACE-Step-1.5/blob/ca1e85fe9430179831e6bc6be790c332190a3866/acestep/constants.py . Accepted language code is not proof of pronunciation or lyric fidelity.
- No unofficial Suno API or artist voice cloning. Rights to user lyrics/audio and explicit consent must be enforced upstream.

## Other sources

- https://ai.google.dev/gemini-api/docs/music-generation and https://ai.google.dev/gemini-api/docs/pricing ; https://ai.google.dev/gemini-api/terms (effective March 23 2026: requires adult-directed API clients, supported regions, no competing model development, and paid services for EEA/UK/Switzerland; review product eligibility and paid-service data handling before launch).
- https://elevenlabs.io/docs/overview/capabilities/music ; https://elevenlabs.io/docs/api-reference/music/compose ; https://elevenlabs.io/music-terms
- https://facebookresearch.github.io/audiocraft/model_cards/MUSICGEN_MODEL_CARD.html
- https://huggingface.co/stabilityai/stable-audio-open-1.0 and https://stability.ai/license

## GPU hosting (no activation)

RunPod serverless: portable containers, scale-to-zero workers, charge for active work and potentially cold start/storage; compare actual serverless worker rate (not pod price) at https://www.runpod.io/pricing. Modal: Python-oriented deployment, per-second GPU/CPU/memory rates, volumes and cold starts; https://modal.com/pricing lists L40S at $0.000542/sec (about $1.95/hr), indicative and excludes CPU/RAM, storage, egress and multipliers. Cost model: billed GPU seconds × per-second rate + CPU/RAM/storage/egress; do not substitute inference wall time for billed time. A hypothetical 60 billed GPU seconds at that rate costs $0.03252 before other fees, not a measured song cost. Require per-job reservation, concurrency ceiling, idle shutdown, absolute account budget and separate telemetry. Start with RunPod/Modal comparison only after owner approval; no resources created.

## Editing and separation

ACE supports cover/repaint and variant-specific extract/complete tasks upstream; test rights-cleared reference audio in a separate contract after M1. No native guarantee of arbitrary extension or separated stems. Demucs htdemucs is a candidate for estimated four-stem separation, not original multitrack recovery; code MIT (https://github.com/facebookresearch/demucs), verify pretrained checkpoint terms, pin hashes and benchmark leakage before enabling. FFmpeg normalization implemented in audio.py; remixing via gain/mix/crossfade is feasible but not equivalent to generative remix or extension. No editing endpoints or paid services enabled. Librosa beat and spectral analysis and Pedalboard mastering are optional future dependencies, not required for the base engine.

## Outstanding acceptance

No GPU credentials, approved budget or live inference used. No claimed quality, language, cost or latency outcomes. Verify real responses against adapters, actual model revision and upstream configuration, cancellation/reconciliation, licensing/account terms, actual cost and native-listener benchmarks. Lead must ratify worker import/callback contract and ensure global billing and job state boundaries. 
