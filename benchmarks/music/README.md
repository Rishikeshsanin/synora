# Reproducible music benchmark

Run from repository root, with Python 3.12 and FFmpeg/ffprobe on PATH. No API requests occur by default.

```sh
python -m unittest discover -s engines/music/tests -v
python -m benchmarks.music.run --provider fixture --output /tmp/synora-fixture-run
# ONLY after approved provider configuration and budget:
python -m benchmarks.music.run --provider ace-step --provider lyria --repeats 3 --allow-real --budget-usd APPROVED_AMOUNT --output /private/new-run
```

Identical canonical specs, original lyrics and repeat seeds are used. Providers may translate controls differently; Lyria does not expose seeds. The 90-second case intentionally tests a duration beyond Lyria Clip. Use new output directories. The harness records the prompt set hash, platform, model/revision, cost reservation estimates, client CPU time, wall time, actual duration and decoded artifact stats. Client CPU is not GPU inference usage. Actual billed cost, GPU peak memory, compute time and subjective scores remain null until external telemetry/listening is collected. No placeholder scores. Failed and unsupported requests are separate, and failed requests are not retried.

## Human assessment

After owner approval, use at least three listeners per generated item; include fluent Telugu and Hindi listeners. Blind/randomize the real-provider audio, keep fixture samples out of rankings, rate each item independently on 1–5:
- Musical coherence and transitions
- Audio fidelity (distortion, clipping, artifacts, unwanted silence)
- Requested genre, instruments and mood adherence
- Vocal intelligibility, lyric accuracy, pronunciation (N/A for instrumental)
- Instrumental-only adherence (N/A for vocals)
- Suitability for advertising, when applicable

Anchors: 1 = unusable, 3 = acceptable with editing, 5 = highly usable as delivered. Record each score, rater ID, item ID, notes, and N/A separately. Report median and spread by provider/case; do not collapse unmeasured metrics into zeros. For lyrics, use native speaker transcription and report word or character error rate separately with normalization policy. Measure BPM with a pinned beat tracker if feasible; verify half/double tempo by ear. Collect peak GPU memory from actual worker instrumentation and billing from provider logs; benchmark cold/warm separately. Preserve raw artifacts, no loudness postprocessing before objective metrics. Listening copies may be level-matched with original preserved. No actual real-provider results have been collected.
