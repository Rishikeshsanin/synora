# Wave 3 — music quality remediation

Base integration candidate 457c5fa4d0536e28dcb4274cc6960834dbeb8bb0. Source fix f51b18d9706a0c3bfeca56ad276dee4e11f1fe88. Latest master #3 comment 7227857714 read; PR #13 and #21 inspected.

## Actual prior CI

- [Master run 46065771578 music job 140730693940](https://github.com/Rishikeshsanin/synora/actions/runs/46065771578/job/140730693940): 15 tests, 1.573s, successful on Python 3.12.
- [PR #21 run 46066021523 music job 140731494874](https://github.com/Rishikeshsanin/synora/actions/runs/46066021523/job/140731494874): 15 tests, 2.010s, successful.
- [PR #21 quality job 140731494684](https://github.com/Rishikeshsanin/synora/actions/runs/46066021523/job/140731494684): audit reported no known vulnerabilities; Ruff 13 F401 issues; explicit namespace package bases resolved duplicate module errors, leaving three missing imports from the backend-dependent optional smoke. Fixes: explicit public __all__, remove unused Path/patch, move the backend smoke into benchmarks/music with compatibility wrapper. DevOps retains namespace package bases and hashed tooling lock; smoke is to be tested/typechecked in backend environment, not deleted or skipped. No shared CI or lockfile modifications.
- Coordinated #2 comment 7227886376 and #5 comment 7227886909. Lead ratified 12 tags/category, 64 chars/tag, 32 language chars and nonempty supplied lyrics. Added backend acceptance parity check. Existing fixture generator algorithm unchanged.
- Hardened malformed ACE status/audio references (only same-origin relative audio route with one nonempty path parameter, no controls), preserve upstream IDs for failed/incomplete Lyria responses, include connection opening in HTTP deadline, clean up partial writes. These are defense-in-depth; no live provider traffic.

## Actual new-code execution (supplemental)

Local container Python 3.13.5, FFmpeg 7.1.5-0+deb13u1, Pydantic 2.13.5. Network checkout still unavailable, but existing Wave 2 copies matched integration Git blob SHA-1. Applied source changes locally and verified all eight engine Python files and the benchmark smoke match exact f51b18d Git blobs; unchanged benchmark runner/prompts and backend model/provider hashes matched integration. Executed:
- python -m unittest discover -s engines/music/tests -v: 17/17 passed, 2.447s. Two new provider regression tests cover nine ACE malformed responses and four Lyria terminal/incomplete statuses.
- PYTHONPATH=apps/api:. python -m benchmarks.music.verify_backend_boundary: 4/4 artifact cases, all tampering rejected, shared flags and 9/9 API/engine boundary acceptance cases passed.
- SYNORA_ENV=development SYNORA_REAL_MUSIC_APPROVED=0 python -m benchmarks.music.run --provider fixture --output /tmp/synora-wave3-fixture: 9/9 cases, 330.0 decoded seconds, zero duration error, 10,560,396 bytes, median wall time 0.366376634s, estimated $0. All nine artifact SHA-256 hashes match Wave 2 evidence (no fixture regression). All simulated, no music quality/adherence/GPU measurements.

Local Python 3.12, Ruff and mypy are unavailable; do not assert new-code 3.12/lint/type gate passed until combined CI with #21 or newer DevOps patch. Prior 3.12 evidence is valid only for exact prior candidate. Full worker/RLS owned by Agent 2/QA. No real inference. See benchmarks/music/ACE_INTERACTIVE.md for a single explicitly authorized offline-after-download GPU experiment; no resources started. 
