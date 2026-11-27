"""Bounded audio validation, metadata and optional mastering using FFmpeg."""
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from .core import MusicError

MAX_AUDIO_BYTES = 80 * 1024 * 1024

def run(args, timeout=60):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True)
    except (OSError, subprocess.SubprocessError):
        raise MusicError("audio processing failed or timed out") from None
    return result

def inspect_audio(path, timeout=60):
    path = Path(path).resolve()
    if not path.is_file() or not 12 <= path.stat().st_size <= MAX_AUDIO_BYTES:
        raise MusicError("audio artifact missing or outside size bounds")
    probe = run(["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-show_streams", "-show_format", "-of", "json", str(path)], timeout)
    try:
        data = json.loads(probe.stdout)
        streams = data["streams"]
        if len(streams) != 1 or streams[0]["codec_type"] != "audio":
            raise ValueError()
        stream = streams[0]
        duration = float(data["format"]["duration"])
        rate, channels = int(stream["sample_rate"]), int(stream["channels"])
        if not math.isfinite(duration) or not 0 < duration <= 600 or not 8000 <= rate <= 192000 or channels not in (1, 2):
            raise ValueError()
        formats = data["format"]["format_name"].split(",")
        mime = next(m for f,m in (("wav","audio/wav"),("mp3","audio/mpeg"),("flac","audio/flac")) if f in formats)
    except (KeyError, TypeError, ValueError, StopIteration):
        raise MusicError("invalid or unsupported audio metadata") from None
    decoded = run(["ffmpeg", "-nostdin", "-v", "info", "-xerror", "-protocol_whitelist", "file", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"], timeout)
    def volume(key):
        match = re.search(key + r":\s*(-?[0-9.]+) dB", decoded.stderr)
        return float(match.group(1)) if match else None
    peak = volume("max_volume")
    rms = volume("mean_volume")
    if peak is None or peak <= -80:
        raise MusicError("audio silent or could not be decoded")
    with path.open("rb") as f:
        sha = hashlib.file_digest(f, "sha256").hexdigest()
    return dict(duration_seconds=duration, sample_rate=rate, channels=channels, codec=stream["codec_name"],
                mime_type=mime, peak_dbfs=peak, mean_dbfs=rms, bytes=path.stat().st_size, sha256=sha)

def master(source, destination, timeout=90):
    """Optional loudness targeting, not a claim of studio-quality mastering."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or destination.exists() or destination.suffix.lower() != ".wav":
        raise MusicError("mastering requires a new WAV destination")
    inspect_audio(source, timeout)
    try:
        run(["ffmpeg", "-nostdin", "-n", "-v", "error", "-protocol_whitelist", "file", "-i", str(source),
             "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100", "-c:a", "pcm_s16le", str(destination)], timeout)
        return inspect_audio(destination, timeout)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
