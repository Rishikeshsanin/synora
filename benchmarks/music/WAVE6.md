# Wave 6: controlled genuine music experiments

Base: verified Wave 5 PR #40 head bc15cc249f385d7d8472cd01619000b2334442ee (run 46069602844: 10/10 jobs, music 26/26 in 2.893s, music-quality audit clean, Ruff passed, mypy 11 files clean, 9 parity cases). Master issue #3 comment 7239132709 authorizes branching from this head until combined Wave 5 integration exists. Combined integration still at 439327e when inspected. Preserve #40, rebase/reconcile this draft onto combined Wave 5 head at lead direction. No shared API/CI/dependency/provider changes.

## Distinguish owner evidence from current execution

Master's owner-notebook report (not independently reproduced here; no raw owner audio inspected):
- Single T4, pinned code ca1e85fe9430179831e6bc6be790c332190a3866 and snapshot eb84216a8ece2d56388e401efc28061a0c30a209.
- FP16 instrumental: 15s 12.03s / 5.60 GiB; 60s 14.67s / 5.61 GiB.
- English 30s FP16 seeds 42 and 123: 48,000 NaN latents; failed. FP32 + DiT CPU offload seed123: valid WAV, 28.95s / 9.07 GiB; lyric adherence unconfirmed.
- Telugu same config: valid 30s WAV, 28.93s / 9.07 GiB; owner heard no requested vocals or lyrics: semantic FAIL. Hindi unverified.
- LM disabled in these runs. Owner's next LM experiment not yet observed. Valid WAV is not proof of singing.

## Implemented controls

One local-process invocation per case, batch one, eight steps, seed 42 or 123, private output, no automatic retry, fallback, server, external API or downloads. Operator must use authorized no-charge interactive compute, disconnect network/use a supported offline execution mechanism after obtaining licensed artifacts, stop before quota/charges, and confirm resource headroom. Offline environment flags alone are not network isolation. The CLI requires explicit authorization and rejects production, non-NVIDIA CUDA and insufficient GPU free memory. Auto uses FP16 for instrumental and FP32 + additional DiT CPU offload for vocals. BF16 explicit only on Ampere or newer. Conservative preflight: 8 GiB free for half precision, 12 GiB for FP32; these are engineering guards, not measured capacity guarantees; LM may still exhaust GPU/host memory. MX330 2GB rejected. Monitor host RAM; do not assume 16GB host is sufficient. Stop on any OOM or numeric failure, retain failed manifest, no automatic retry. A subsequent manually selected precision run is a distinct experiment, not a silent retry.

Pinned upstream init_service_orchestrator.py sets CUDA dtype itself, and memory_utils.py has a separate VAE dtype selector. Existing ACESTEP_DTYPE hint in generate_music_decode.py does not implement an actual NVIDIA init setting at this pin. Research subclass pins dtype before loading, overrides VAE device dtype (CPU float32), and checks handler and first floating DiT parameter after init. This is not proof of every operation's dtype. Real GPU execution of this subclass is still required. Pinned decode checks NaN/Inf and zero latents; runner records known failure class only and never stores raw upstream error text. It obtains the post-upstream float tensor with save_dir=None, rejects nonfinite/out-of-range samples before writing PCM16, checks shape, duration (2% or 0.25s), near-silence, near-full-scale fraction, records peak/RMS dBFS and SHA256; no extra normalization. Pinned upstream decode itself may peak-scale values >1; metrics describe returned float tensor, not pre-VAE waveform. RMS is not LUFS. Thresholds are technical experiment guards, not musical quality scores.

Stage checkpoint bytes once outside HF cache and source; later runs compare bytes against pinned snapshot, permit only tracked pinned model code sync and reject arbitrary added files/symlinks. Lock prevents concurrent runner use. Rehashing full snapshot + stage costs disk reads but avoids repeated copying; benchmark generation time excludes rehashing. Trust original downloaded snapshot and private workspace, not adversarial concurrent writers. Snapshot name and byte comparison are not external cryptographic attestation. Never remove lock unless no active process; failed partial stage must be inspected and recreated privately. Imports must resolve to checked-out pinned source.

## Controlled language evaluation

Seven cases: 15/60s instrumental; English 30s control; Telugu native/romanized 30s; Hindi native/romanized 30s. All vocal cases have same caption, 90 BPM, language code, seed, duration and settings; paired original two-line lyrics represent same content in each language (romanization is an approximation, not phonetic ground truth). Start FP32, seed123, LM off. Compare exactly the same case with --lm semantic-pt only if authorized compute and memory permit. Do not conflate precision or seed changes with LM effects. Review each actual artifact against expected language/lyrics, vocals, coherence and style; technical success is pending human review. Missing vocals, wrong language or wrong lyrics is fail; null = unknown. Native speaker listening is required for lyric fidelity. English control must also be reviewed. No quality scores assigned from owner valid WAV or local synthetic data.

LM path: pinned inference.py uses thinking=true plus initialized LM and absent provided codes to request llm_dit (two phases, metadata and semantic codes), whereas CoT-only requests use dit. Use existing 1.7B checkpoint, PT backend, FP32, CPU offload; disable CoT caption/metas/language changes and preserve supplied lyrics. Require nonempty returned audio_codes, record only length/hash, not tokens. use_cot_lyrics is not consumed by inference at this pin. LM semantic codes present do not prove accurate vocals. Alternative: 0.6B LM may reduce memory, requires separately pinned revision/license and actual evaluation; not downloaded/activated. Lyria remains optional gated commercial adapter with no free inference assumption. MusicGen weights' noncommercial restrictions and TTS speech (not singing) make neither an automatic commercial fallback. No unauthorized voice cloning, reference tracks or public Kaggle service.

## Commands

Use already authorized pinned ACE Python 3.12 venv, original HF snapshot and private parent directories, from Synora root. See ACE_INTERACTIVE.md for the existing manual permitted download procedure. First run only, add --prepare-checkpoints if stage does not yet exist. Reuse stage for other cases; no repeated copies. One case per command:
```sh
PYTHONPATH="$PWD" /path/to/ace-pinned/.venv/bin/python -m benchmarks.music.ace_wave6 \
  --ace-source /path/to/ace-pinned \
  --snapshot /path/to/models--ACE-Step--Ace-Step1.5/snapshots/eb84216a8ece2d56388e401efc28061a0c30a209 \
  --checkpoint-dir /private/ace-stage --output /private/en-fp32-lm-off \
  --case english --precision auto --seed 123 --lm off --authorized-offline-no-charge
```
Use different output paths for each invocation; choose --case telugu-native / telugu-roman / hindi-native / hindi-roman / instrumental15 / instrumental60. Never batch unattended quota-consuming experiments. Compare same seed with --lm semantic-pt (manual single experiment). Explicit --precision fp16 for controlled regression only; not recommended for T4 vocals. If GPU gate blocks, stop.

After actual listening, create private review_input.json with exact audio_sha256 from experiment.json, listened_to_exact_artifact=true and booleans/null for musical_coherence, requested_style, vocals_present, language_match, lyrics_match (instrumental_only instead of vocal fields for instrumental). Then run:
```sh
python -m benchmarks.music.wave6_quality /private/en-fp32-lm-off /private/review_input.json
```
Creates exclusive review.json bound to exact audio hash, exit 0 only if human-attested rubric passed; 2 if fail/pending. Human review does not independently prove inference origin; no automatic upload. Avoid private/customer lyrics or identity; only original test lines. No master approval implied. Existing Wave 4 notebook/verifier preserved; Wave 6 manifest schema deliberately separate.

## Licensing and references

- Pinned upstream [MIT code license](https://github.com/ace-step/ACE-Step-1.5/blob/ca1e85fe9430179831e6bc6be790c332190a3866/LICENSE) independently read: retain notice.
- [Pinned model snapshot](https://huggingface.co/ACE-Step/Ace-Step1.5/tree/eb84216a8ece2d56388e401efc28061a0c30a209): Wave 1/2 research recorded MIT model metadata; separate review of model/LM/VAE/text encoder and transitive dependencies and distribution notices mandatory before product release. License metadata not legal clearance or output rights guarantee.
- [Pinned inference implementation](https://github.com/ace-step/ACE-Step-1.5/blob/ca1e85fe9430179831e6bc6be790c332190a3866/acestep/inference.py), [CUDA initialization](https://github.com/ace-step/ACE-Step-1.5/blob/ca1e85fe9430179831e6bc6be790c332190a3866/acestep/core/generation/handler/init_service_orchestrator.py), [VAE dtype policy](https://github.com/ace-step/ACE-Step-1.5/blob/ca1e85fe9430179831e6bc6be790c332190a3866/acestep/core/generation/handler/memory_utils.py), [latent rejection and peak guard](https://github.com/ace-step/ACE-Step-1.5/blob/ca1e85fe9430179831e6bc6be790c332190a3866/acestep/core/generation/handler/generate_music_decode.py), [LM init](https://github.com/ace-step/ACE-Step-1.5/blob/ca1e85fe9430179831e6bc6be790c332190a3866/acestep/llm_inference.py) examined directly at pin.

## Actual local tests

Python 3.13.5, torch 2.10.0+cpu, no CUDA. DNS prevents local GitHub checkout; standalone exact three new files executed in temporary namespace tree, not combined 34-test suite. Eight new tests 8/8 in 0.159s, py_compile passed, real CLI refused CPU-only environment (exit 2, no stage/output). Synthetic 440Hz mono 48kHz 15s tone accepted by quality writer; ffprobe 15.000000s, 1,440,044 bytes, PCM16; full ffmpeg -xerror decode exit 0. Peak -13.9794 dBFS, RMS -16.9897 dBFS, zero near-full-scale fraction; semantic pending. See evidence JSON. Stage regression used tiny artificial files only, no actual weights. Exact Git blob checks required before commit. No audio samples uploaded. New GPU path, Python 3.12 CI, Ruff/mypy and full integrated tests remain pending. Agent #2/#6 notified. No paid resources, dependencies, main changes or deployment.
