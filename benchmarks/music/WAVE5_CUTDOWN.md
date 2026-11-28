# Wave 5: CPU soundtrack cutdowns

Base 439327e8d4ad2910b349cf5e74bbd53e1aeed92a, verified all ten jobs green in run 46068373250. Music job 140739215940 passed 20 tests in 2.355s; music-quality job 140739215719 passed Ruff, mypy (9 files), strict audits and backend smoke (4 artifact cases and 9 validation cases). These are exact **baseline** results, not results from this branch.

## Functionality

Local-only, deterministic PCM16 WAV editor for existing rights-cleared soundtracks: sample-accurate trim, repeat with optional linear crossfade, fade in/out and exact target length 1–120s. Preserves channels and sample rate (mono/stereo, 8–48 kHz), source and previous output files. Selection 250ms–120s, source <=600s/80MiB; bounded processing, no GPU, no Python package downloads. User attests derivative rights and source category. Manifest carries source/output SHA-256 and edit parameters; simulated fixture stays marked. User-supplied source kind is not an origin or rights verification. This is audio editing, **not AI composition**, beat detection, seamless musical phrase arrangement, stem separation or a new provider. No API/UI/production exposure. Local trusted paths only; future backend adapter needs private attempt directories, ownership and rights enforcement, cancellation, upload validation and provider-specific permission (e.g. do not assume transformation rights from possession of an audio file). Never remove watermarks.

## Execute from repository root

```sh
python -m unittest discover -s engines/music/tests -v
python -m engines.music.cutdown private/source.wav private/30s.wav --end-ms 8000 --target-ms 30000 --crossfade-ms 250 --fade-in-ms 200 --fade-out-ms 400 --source-kind user-owned --rights-confirmed
```

Use --rights-confirmed only if actual derivative permission exists; choose simulated-fixture for synthetic sources. Output must be a new file. JSON manifest prints to stdout; redirect to a private file. The CLI does not open a network connection. For shorter trim targets use --crossfade-ms 0. The overlap can smooth repeat boundaries but cannot guarantee musical continuity.

## Actual local evidence

Container Python 3.13.5, FFmpeg 7.1.5, CPU-only torch 2.10.0+cpu (zero CUDA devices). Direct Git checkout DNS failed; copied neither existing engine nor old tests for this run. Executed exact new standalone source/test files in a temporary namespace-package tree. Six new unit tests passed (latest 0.095s), not a full integrated test run. Git blob hashes: cutdown.py 0e015d92353024eea3d36af15275bc035b319d92; test_cutdown.py 15d46d7d7b0b6d1eab829ddc926902de800d8025. Compare remote hashes before integration. Existing engine and dependency locks untouched.

Ran real CLI four times with an original FFmpeg 8-second 440Hz stereo tone, no AI:
```sh
mkdir -p /tmp/synora-wave5-demo
ffmpeg -nostdin -v error -f lavfi -i 'sine=frequency=440:sample_rate=48000:duration=8' -ac 2 -c:a pcm_s16le /tmp/synora-wave5-demo/source.wav
for ms in 15000 30000 60000 120000; do
  /usr/bin/time -f 'elapsed=%e s peak_rss=%M KiB' python -m engines.music.cutdown /tmp/synora-wave5-demo/source.wav /tmp/synora-wave5-demo/cut-$ms.wav --end-ms 8000 --target-ms "$ms" --crossfade-ms 250 --fade-in-ms 200 --fade-out-ms 400 --source-kind simulated-fixture --rights-confirmed > /tmp/synora-wave5-demo/cut-$ms.json
  ffprobe -v error -show_entries format=duration,size -of json /tmp/synora-wave5-demo/cut-$ms.wav
  ffmpeg -nostdin -v error -xerror -i /tmp/synora-wave5-demo/cut-$ms.wav -f null -
done
```
All four full decodes and exact target durations verified. See evidence/wave5-cutdown.json. Linux container process RSS and wall time are not MX330 laptop performance claims. No audio or model weights uploaded to GitHub. No new Python dependencies, paid API or inference.

## Continuation

No owner GPU dependence. Genuine ACE-Step still blocked (no CUDA/model in current environment); MX330 2GB is not a viable assumption for large models. Do not launch rentals, evade quotas or rely on unverified CPU feasibility. Existing guarded notebook remains an authorized-future path. No actual AI quality measurements. Ask lead to review a future local editing API contract, cancellation/resource limits, source ownership, source provider rights and provenance before surfacing UI controls. Agent 2/4 informed of scope. Run exact Python 3.12 combined unit suite and existing Ruff/mypy/audit/CI gates; local tools unavailable. No merges/deployments.
