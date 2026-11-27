# Wave 2 — offline media only

Base integration/m1-foundation at 6cc2bc1f314fb80bd9eca39f68e8b7dfc0c01759. Existing Wave 1 files untouched. New local modules are proposals, not production contracts.

## Run and CI handoff
Use an isolated Python 3.12 environment with FFmpeg/ffprobe and enough scratch space (up to ~3 GB per HD job). Candidate pins reflect installed dependency graph evaluated for 3.12 markers. Local environment is Python 3.13.5; network DNS blocked both Python 3.12 download and PyPI resolution. Do NOT call the candidate constraints a verified hashed lock. DevOps #5 should resolve and commit actual hashes on Python 3.12 with registry access:

    python3.12 -m venv .venv
    . .venv/bin/activate
    uv pip compile --python-version 3.12 --generate-hashes -c engines/media/requirements-py312.constraints.txt engines/media/requirements.txt -o engines/media/requirements-dev.lock
    python -m pip install --require-hashes -r engines/media/requirements-dev.lock
    python -m unittest benchmarks.media.test_offline benchmarks.media.test_wave2 -v
    OPENBLAS_NUM_THREADS=1 python -m benchmarks.media.wave2_demo /tmp/synora-wave2-fresh

Do not silently relax pins or skip tests if resolver fails. Record error, agree corrected pins, re-run both demos. Wave 2 remains nonblocking for M1; separate optional media job with artifacts and hashes, no live endpoints or secrets.

## Safety and design
Four deterministic concepts, transparent matched brief fields and stable scores; no semantic/AI inference in ranking. HMAC-SHA256 binds canonical storyboard, ratio, image and soundtrack SHA-256, captions, evidence, reviewer, issuance/expiry; minimum 32-byte trusted key; digest alone is not accepted by v2. Trusted caller controls key, reviewer, local path mapping and human source review. Replay within TTL is allowed; no authenticated identity, revocation or job-level replay control. Legacy CLI remains for local demos only, never route production to it. All non-neutral captions must exactly match reviewed source extract (UTF-8 file bytes), ID and digest. This proves exact source correspondence, not independent truth/legal compliance. A dishonest trusted reviewer could approve a false source; production needs verified provenance, evidence scope and human advertising review.

Read bounded bytes once, hash and decode the same bytes; no cropping or generative edits to product, proportional LANCZOS with EXIF orientation. No colour-managed ICC/alpha or perceptual fidelity guarantees; encoded H.264 is lossy. HD with caption-safe regions, eased scale, audio fades, BT.709 metadata, faststart, exclusive publication after probe and decode QC. ASCII only, three scenes of four beats, PCM16 WAV only, max 20s rendered and 60s soundtrack. Raw frames can require ~3 GB scratch; no untrusted paths or production concurrency. Synthetic fixture approval is automatic and marked simulated. No scene caching yet; no Remotion runtime, voiceover, actual generative imagery or M1 adapter.

## Semantic and visual provider investigation (2026-11-28)
- Tesseract 5.5.0 local: actual English OCR recovered AUREL and DEMO from all 3 synthetic product fixtures using --psm 11. Not logo recognition, no confidence/calibration or real-photo benchmark. Candidate for extracting evidence observations only; never assert OCR as verified facts.
- Florence-2-base, official Transformers-converted 0.23B checkpoint, MIT model card, detection/captioning/OCR candidate: https://huggingface.co/florence-community/Florence-2-base ; original Microsoft card https://huggingface.co/microsoft/Florence-2-base . Pin exact revision and review runtime/dependency licenses before activation; no model downloaded or run. Prefer native Transformers implementation without unreviewed remote code.
- SigLIP2 base patch16 224 Apache-2.0, image/text similarity candidate, observed revision 0ad8c6e0ff16615356a08a1ad8c8bbc8930c434e: https://huggingface.co/google/siglip2-base-patch16-224/tree/0ad8c6e0ff16615356a08a1ad8c8bbc8930c434e . Similarity is not an authenticity guarantee; benchmark on near-duplicate package variants.
- FLUX.1-schnell Apache-2.0 model card: https://huggingface.co/black-forest-labs/FLUX.1-schnell ; commercial use permitted by stated model license, compute still costs money, no GPU performance or SaaS rights benchmark. Candidate for backgrounds only, never synthetic replacement of product/logo. FLUX.1-dev noncommercial weights not approved; https://github.com/black-forest-labs/flux . Pin revision, review all component licenses before testing.
- Google Imagen 4 Ultra published $0.06/image: https://cloud.google.com/model-garden/pricing . Three backgrounds nominal $0.18 before retries/storage/taxes; not free, no account or API activated. Pricing/model/region and data terms must be verified at procurement. No unlimited free service assumed.

Next: realistic rights-cleared photo set (labels, reflective packages, transparent products), annotated OCR and logo region benchmark, audio beat ground truth, multilingual typography, color-managed pipeline, per-scene content hashes/cache and disk streaming, production auth/claim evidence only after lead ratification. No model inference cost incurred.
