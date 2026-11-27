#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
PYTHON="${PYTHON:-python3.12}"
"$PYTHON" -c 'import sys; assert sys.version_info[:2] == (3, 12), "Python 3.12 required"; print(sys.version)'
command -v ffmpeg
command -v ffprobe
ffmpeg -version | head -n 1
ffprobe -version | head -n 1
export SYNORA_ENV=development SYNORA_REAL_MUSIC_APPROVED=0
export SYNORA_ACE_APPROVED=0 SYNORA_LYRIA_APPROVED=0
"$PYTHON" -m unittest discover -s engines/music/tests -v
"$PYTHON" -m benchmarks.music.run --provider fixture --output "${1:?provide a new output directory}"
