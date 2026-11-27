# Wave 5: CPU-only selective scene regeneration

Base: 439327e8d4ad2910b349cf5e74bbd53e1aeed92a. Implementation: d438d3fa8ae18ef4e39659080d74fad345da23da. Issue #4 checkpoint. Master CI 46068373250: all 10 jobs success; media job 140739215681 passed strict audit, Ruff, mypy (6 files), 25 tests, legacy, HD, editorial, campaign renders and artifact publication. Audited dependencies, existing source files, workflows and contracts unchanged. Three new source blobs exactly matched locally tested files.

## Functionality and security boundary

Opt-in local render_incremental accepts existing signed M2 storyboard and immutable source paths. Full board approval, evidence, image/audio bytes and rights checked before cache access; changed caption requires new approval. Separate video-only H.264 scene clips are keyed by image byte hash, caption, dimensions, presentation, position, frame count, 24fps and engine fingerprint (Pillow version, FFmpeg version, renderer/layout source). Clip manifest is HMAC-authenticated with a domain separator and source key, and SHA-256 checked on bounded read; unauthenticated or corrupted clip misses and is regenerated. Cache scope: one trusted local project/process, caller-controlled private directory, 0700 check on POSIX; Windows ACL not independently enforced; no multi-user service, concurrency guarantee, encryption or persistent key store. Cache max 24 entries, 24 MiB per clip and 128 MiB aggregate MP4 payload; full cache bypasses writes, no eviction. Metadata is separately bounded on read. Do not share a cache or key between users. Clear cache when rights are revoked; lifecycle and deletion service not implemented. Existing production auth/approval contract remains unapproved.

Stream one RGB frame at a time to CPU libx264 with two encoder threads, no raw RGB disk spool, no GPU or AI model. Each new clip is probed and fully decoded before cache insertion. Concatenate video-only clips without re-encoding, mux approved audio with fades, probe streams and frame counts and decode entire result before exclusive atomic publication. Original renderer preserved. Retiming recomputes frame counts and invalidates affected clips; audio remux occurs each render. Music-only edit with same scene timings is structurally supported but not independently benchmarked here. Clip timing currently uses existing four-beat/three-scene timeline, max 480 frames, 24fps, HD only. Existing rights and claim safeguards retained; human rights assertion is not independent licensing proof. No new dependencies.

## Executed verification

Local Linux Python 3.13.5, Pillow 12.3.0 (older vulnerable local version; trusted synthetic fixture only), FFmpeg 7.1.5, NumPy 2.3.5 and Librosa 0.11.0. Audited Python 3.12/Pillow 13 baseline was verified via CI; new branch patched-runtime checks pending at handoff. Ruff/mypy unavailable locally.

`OPENBLAS_NUM_THREADS=1 python -m unittest discover -s benchmarks/media -p 'test_*.py' -q`: 32/32 passed in 3.705s. Seven added tests: render input key variation, authenticated cache, corrupt clip/manifest, capacity limits, changed approval, missing evidence before cache, real FFmpeg uneven timing (80 frames at 360x640, injected beat timestamps only) and corrupt clip recovery (only scene 2 regenerated, identical output bytes). Existing 25 tests unchanged.

Actual HD demo uses original fictional same-SKU illustrations and original synthetic audio, no generative AI, rights cleared fixture. Real beat detection. Each run generates original, separately approved revision of middle caption, and unchanged repeat. All 9 internal full decodes and independent ffprobe checks passed; 144 frames/6s, H264/AAC, 24fps, cut frames 48/96. Independent FFmpeg framemd5 of decoded original/revision confirmed all 96 unchanged scene frames identical and middle 48 different, across each ratio. Repeat identical SHA256 to revision. Source code hashes checked against local executed files. No binaries committed.

| Ratio | Cold full render | Edit one scene | Repeat | Peak RSS (GNU time -v, max process/child, not aggregate memory) | Cache clip bytes after edits |
|---|---:|---:|---:|---:|---:|
| 9:16 | 9.723s | 2.950s | 0.602s | 339204 KiB | 347402 |
| 16:9 | 9.341s | 2.850s | 0.618s | 341284 KiB | 342942 |
| 1:1 | 7.759s | 2.056s | 0.567s | 299424 KiB | 237906 |

Cold render includes first Librosa initialization; not controlled same-warmth speed comparison, not a laptop benchmark. All three revisions 2 hits/1 encode, repeat 3 hits/0 encode. First combined command hit execution timeout after first two ratios; square completed separately in a fresh directory. Profile exit status 0 for each completed command.

Output SHA-256 (original / revised and repeat):
- 9:16 281883f272b8486687b88b79a3f1005bc8cd35e17c27f355cdce28b8e98d002d / 7f7ec19939337b0d8896a6d89861cab90cbf1c228eb1e1865b850802498a8c33
- 16:9 52ab598705562e614a9cdfc6898e8becf9c59b3256f4e6db8a6e4583455078e9 / 0db58d4bcbae7b292c521c743f28f565c71995bf2e7f1f77a095592d63e2d13b
- 1:1 7ada19ae9cbea712de83579af8e1f4265d00cf6f54e78fe4525f447df4987009 / e39fc0e633f0a6e1a54b566dedebc0a9b8b9486f6fc9ccce8f34c6315727da81

## Reproduce and continuation

From repository root, installed audited engines/media/requirements-dev.lock, FFmpeg/ffprobe on PATH, fresh local private work directories:
    OPENBLAS_NUM_THREADS=1 python -m benchmarks.media.wave2_demo /tmp/synora-wave2
    python -m benchmarks.media.campaign_fixture /tmp/synora-campaign
    OPENBLAS_NUM_THREADS=1 python -m benchmarks.media.incremental_demo /tmp/synora-campaign/manifest.json /tmp/synora-wave2/original.wav /tmp/synora-revision-vertical 9:16
Repeat with fresh output dirs and 16:9 / 1:1. Demo key is ephemeral and private; repeat inside same invocation proves cache. Do not upload private-cache, keys, or arbitrary user assets; only synthetic original.mp4, revised.mp4, repeat.mp4 and results.json can be allowlisted for CI. Existing test discovery automatically includes new tests. Coordinate #5 for artifact demo step, no workflow edits in media PR.

Owner MX330 2GB not used; no GPU, no downloaded model, no paid API, no Railway, no production deployment. No new generative AI capability claimed. Next: confirm actual branch CI against audited environment; independent alternative soundtrack and uneven real music beat detection, longer timeline and Windows ACL/NTFS behavior, production project-scoped cache isolation/expiry/cancellation and resource budget only after approved shared contracts. Keep real photo/semantic model evaluation pending authorized weights and rights-cleared photos. No merge authority.
