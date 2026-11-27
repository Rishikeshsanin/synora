# Wave 2 local evidence
Python 3.13.5, FFmpeg 7.1.5, Pillow 12.3.0, numpy 2.3.5, librosa 0.11.0; no external inference or paid spend. Base four Wave 1 source Git blob hashes matched local checkout. Command: python -m unittest benchmarks.media.test_offline benchmarks.media.test_wave2 -v: 16/16 passed in 0.214s (7 legacy + 9 new). Includes 9 pre-encoding fidelity checks across ratios and animation progress, signed approval alterations, expiration, wrong key, unsupported caption, source mismatch, image/audio byte tampering. Synthetic fixture is not a real advertisement quality benchmark.

Command: OPENBLAS_NUM_THREADS=1 python -m benchmarks.media.wave2_demo /mnt/data/synora-wave2-demo
- 9:16 1080x1920, 144 frames, 6s, 8.77s wall, SHA256 ae03eb66ba84269dea6164947cf8f6b62a9ca9e4a9ac054d53b5ac351fccd783
- 16:9 1920x1080, 144 frames, 6s, 5.34s wall, SHA256 638f6dd1be3c96ed3354a672d012a5393140a624805f38e14a782a3d30a5499c
- 1:1 1080x1080, 144 frames, 6s, 4.45s wall, SHA256 ff9a7dc41e419881589b015f5faddd02ba74fcc33241d769d26d22a74874986e

Each render passed internal ffprobe and ffmpeg -xerror full decode; independent ffprobe confirmed both streams duration 6.000000, H264/AAC, video bt709, 144 frames and cut frames 48/96 reported by renderer. Output binaries generated locally, not committed; reproduce via demo. SHA describes specific output, not cross-platform bit-for-bit. OCR command tesseract PRODUCT.png stdout --psm 11, Tesseract 5.5.0: all three synthetic fixture images returned AUREL and DEMO. No real-world OCR accuracy claimed. Python 3.12, clean dependency resolution/hashes and CI still pending; network DNS blocked. No production approval.
