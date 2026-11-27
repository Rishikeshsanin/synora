# Wave 3 media verification

Base: integration/m1-foundation at 457c5fa4d0536e28dcb4274cc6960834dbeb8bb0.
Implementation commit: 2a11b4804fc762bd40acf599fbb8634cd28dc590.
All 11 implementation Python file Git blob hashes matched the locally executed files.

## Actual CI evidence inspected
- Master PR #13: run 46065771578, media job 140730694009 failed strict audit (48 vulnerabilities in 2 packages).
- PR #21: run 46066021523, media job 140731494756 failed strict audit (Pillow 12.3.0; reported fixed version 13.0.0) and Ruff (133 errors: E401/E701/E702/F401). Mypy succeeded on 4 source files, 16 tests passed, all three prior HD renders produced.
- Wave 3 removes the reported multi-import, semicolon, inline suite and unused import patterns throughout owned Python paths; actual Ruff executable unavailable locally, so green lint is not claimed. Existing acceptance commands unchanged.
- #5 coordination comment 7227889272 requests DevOps own Pillow direct pins plus actual resolver-generated hashed media lock; intentionally no overlapping dependency edits. Do not merge or use on untrusted data until patched audit passes.

## Local results
Python 3.13.5, Pillow 12.3.0 (vulnerable; isolated trusted fixtures only), existing FFmpeg/Librosa.
`python -m unittest benchmarks.media.test_offline benchmarks.media.test_wave2 benchmarks.media.test_editorial -q`: 18/18 passed in 0.847s.
New tests: 27 source-fidelity comparisons across ratio, scene and animation position; bounds and aspect checks; scene positioning; signed preset tamper and unknown preset rejection. Legacy and Wave 2 tests preserved.

A/B demo using one 600x400 rights-cleared coffee photograph, same synthetic soundtrack and neutral approved captions for both presets. Source: skimage.data.coffee (Rachel Michetti, CC0, courtesy Pikolo Espresso Bar); https://scikit-image.org/docs/0.26.x/api/skimage.data.html#skimage.data.coffee . No actual business endorsement, commercial claims, or generative model usage. Source PNG SHA256 cc02f8ca188b167c775a7101b5d767d1e71792cf762c33d6fa15a4599b5a8de7. Audio from Wave 2 original.wav. Source photo reused in all three scenes, not three distinct camera angles. No binaries committed. To reproduce from root with trusted assets and a fresh directory:
```sh
OPENBLAS_NUM_THREADS=1 python -m benchmarks.media.wave2_demo /tmp/wave2-fixtures
OPENBLAS_NUM_THREADS=1 python -m benchmarks.media.editorial_demo /path/to/cc0-coffee.png /tmp/wave2-fixtures/original.wav /tmp/wave3-ab
```
Initial A/B command was interrupted after four outputs, reattempt refused overwriting existing output; square pair completed separately with HD restricted to 1:1 in the demo process. Six files independently probed and decoded using ffmpeg -v error -xerror -i FILE -f null -. All 144 frames, 6s video and 6s audio, H264/AAC. Three vertical scenes decoded at 1/3/5 seconds and visually inspected in contact sheet. Hashes:
- 16x9 classic 9d37d06d7ce14b3bab4c58a7589a94ff7360e7eb1b3326b93b12e35c14da01a1
- 16x9 editorial b6d55630b33dcf45b77baf4bdbd69e009d532ab5275cb06ec9e17b7ebfaf98d7
- 1x1 classic cca21e03dbc1b39ab29e667bdb7859c32123caa55c75df3c57b1cbeb34f6d85f
- 1x1 editorial d68a66208dcdf905cac16c1ab4459d26126c3169da806e46c6339ab87c4b2b0e
- 9x16 classic b79eff3f08ea8fe0b569e032d247d379297c184a4ec1aa3efbdedc892bd7bf75
- 9x16 editorial d33b48921b6976d71c56d37998ff83a6b129b7ba89e0f78c8bb8227ea480270f

## Scope and limitations
Signed presentation enum classic (default) / editorial-v1; HMAC binds it to board. Warm fixed palette, distinct portrait/landscape layout, editorial numbering, fitting exact approved caption and closing outlined CTA. No new factual copy; no product cropping. Pixel checks before lossy encoding, not ICC-aware or perceptual certification. Uses Pillow default font, no bespoke multilingual typography, multiple physical shots, real music, actual generated imagery, semantic model, scene cache or commercial quality certification. Source photo low-resolution, upscaled, intentionally reused for controlled A/B. Local approval still trusts reviewer and local paths. No M1 contract/workflow/production edits, no paid resources. Next: patched locked Python 3.12 audit/lint/type/test/render verification coordinated with #5; more rights-cleared real products and diverse source shots; brand-customizable signed presentation after lead review.
