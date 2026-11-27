#!/usr/bin/env bash
set -euo pipefail
python3.12 -c 'import sys; assert sys.version_info[:2] == (3, 12)'
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  sudo apt-get update
  sudo apt-get install -y --no-install-recommends ffmpeg
fi
ffmpeg -version
ffprobe -version
