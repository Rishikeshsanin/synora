# Wave 4 — authorized GPU evidence path

Base 2a802b71b36e08684ab6562d21e4f4981984d9b6. Master comment 7228018587, PR #13, #28, issue #29 and CI 46066906111 reviewed. Music job 140734303127 passed 17 tests in 2.352s; music-quality job 140734303034 reported no known vulnerabilities, Ruff all checks passed and mypy no issues in eight source files. No audited lock, workflow, runtime provider or shared API edits.

Actual local hardware preflight: Python 3.13.5, PyTorch 2.10.0+cpu, no CUDA build, zero devices, ACE-Step absent, FFmpeg 7.1.5. No authorized GPU attached or available to this execution environment. No GPU service launched, no model weights downloaded and no genuine audio generated. Preflight exited 2 as intended. See evidence/wave4-preflight.json.

New executable `python -m benchmarks.music.ace_evidence` checks installed runtime without network or inference; `--verify /private/experiment` independently checks WAV, SHA-256, format, duration, telemetry consistency and pinned-model metadata. It explicitly does not attest inference origin or musical quality. Test-only fabricated manifests are used solely to exercise rejection and consistency logic, not presented as genuine evidence. The existing pinned generator remains unchanged. Notebook ACE_Interactive.ipynb provides guarded setup, one manual 15s generation and listening/verification cells. Notebook not executed on GPU; requires explicit permission, compatible hardware, licensed artifacts, offline execution and no new spend. No automatic resource provisioning.

Actual supplemental execution against hash-matched integrated source: baseline 17/17 (2.477s); updated 20/20 (3.304s) on Python 3.13.5. New helper blob 3dc7e63a9c65c2bd65afe36be1377cb7b751df00 and tests blob 9188935fe68d14be226b86e5bcd97369099f80e2 matched local tested source. Nine fixture cases passed, 330s decoded, zero duration error, 10,560,396 bytes, median wall time 0.377772533s, all nine SHA-256 matched prior Wave 3 artifacts. Backend smoke: four artifact checks, nine input parity cases passed. No genuine music or quality score. New-code Python 3.12, Ruff/mypy CI still mandatory; no gates weakened.

Reproduce from root:
```sh
python -m unittest discover -s engines/music/tests -v
python -m benchmarks.music.run --provider fixture --output /tmp/new-fixture-run
PYTHONPATH=apps/api:. python -m benchmarks.music.verify_backend_boundary
python -m benchmarks.music.ace_evidence
```
Last command is expected to exit 2 on CPU-only/unprepared hosts. To collect genuine evidence use ACE_Interactive.ipynb or the existing ACE_INTERACTIVE.md instructions in an authorized local environment. No production inference enabled. No overlap with #29 (authenticated Studio harness).
