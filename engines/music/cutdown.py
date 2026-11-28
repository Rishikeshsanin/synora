"""Bounded, local PCM soundtrack editing; never a music-generation provider."""
from __future__ import annotations

import argparse
from array import array
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import wave

MAX_SOURCE_BYTES = 80 * 1024 * 1024
MAX_EDIT_MS = 120_000
SOURCE_KINDS = ("user-owned", "licensed", "simulated-fixture")


class CutdownError(ValueError):
    """Invalid or unsupported local soundtrack edit."""


@dataclass(frozen=True)
class EditSpec:
    start_ms: int
    end_ms: int
    target_ms: int
    crossfade_ms: int = 0
    fade_in_ms: int = 0
    fade_out_ms: int = 0

    def __post_init__(self) -> None:
        values = (self.start_ms, self.end_ms, self.target_ms, self.crossfade_ms,
                  self.fade_in_ms, self.fade_out_ms)
        if any(type(value) is not int for value in values):
            raise CutdownError("edit times must be integer milliseconds")
        if not 0 <= self.start_ms < self.end_ms <= 600_000:
            raise CutdownError("invalid source window")
        window = self.end_ms - self.start_ms
        if not 250 <= window <= MAX_EDIT_MS or not 1000 <= self.target_ms <= MAX_EDIT_MS:
            raise CutdownError("window must be 250–120000ms and target 1000–120000ms")
        if not 0 <= self.crossfade_ms <= min(2000, window // 2):
            raise CutdownError("invalid repeat crossfade")
        if self.crossfade_ms and self.target_ms <= window:
            raise CutdownError("repeat crossfade requires a target longer than the window")
        if min(self.fade_in_ms, self.fade_out_ms) < 0 or self.fade_in_ms + self.fade_out_ms > self.target_ms:
            raise CutdownError("invalid endpoint fades")


def _frames(ms: int, rate: int) -> int:
    return (ms * rate + 500) // 1000


def _compose(source: array[int], channels: int, target: int, overlap: int) -> tuple[array[int], int]:
    length = len(source) // channels
    result = source[:min(length, target) * channels]
    repeats = 0
    while len(result) // channels < target:
        tail = len(result) - overlap * channels
        for frame in range(overlap):
            weight = frame + 1
            for channel in range(channels):
                a = tail + frame * channels + channel
                b = frame * channels + channel
                result[a] = (result[a] * (overlap + 1 - weight) + source[b] * weight) // (overlap + 1)
        remaining = target - len(result) // channels
        take = min(remaining, length - overlap)
        result.extend(source[overlap * channels:(overlap + take) * channels])
        repeats += 1
    return result, repeats


def _fade(samples: array[int], channels: int, frames: int, fade_in: int, fade_out: int) -> None:
    for count, reverse in ((fade_in, False), (fade_out, True)):
        for step in range(count):
            frame = frames - 1 - step if reverse else step
            for channel in range(channels):
                i = frame * channels + channel
                samples[i] = samples[i] * step // max(1, count - 1)


def edit_wav(source: Path, destination: Path, spec: EditSpec, *,
             rights_confirmed: bool, source_kind: str) -> dict[str, object]:
    """Trim/repeat a private rights-cleared WAV. Keep source and prior exports immutable.

    Rights and source kind are caller attestations, not license or origin verification.
    Only trusted local paths are accepted; this is not an upload or storage API.
    """
    if rights_confirmed is not True or source_kind not in SOURCE_KINDS:
        raise CutdownError("explicit derivative rights and source kind required")
    if source.is_symlink() or not source.is_file() or source.suffix.lower() != ".wav":
        raise CutdownError("source must be a local WAV regular file")
    if destination.suffix.lower() != ".wav" or destination.exists() or destination.is_symlink():
        raise CutdownError("destination must be a new WAV file")
    try:
        with source.open("rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 44 <= info.st_size <= MAX_SOURCE_BYTES:
                raise CutdownError("source exceeds file bounds")
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
            stream.seek(0)
            with wave.open(stream, "rb") as reader:
                rate, channels, length = reader.getframerate(), reader.getnchannels(), reader.getnframes()
                if (reader.getcomptype() != "NONE" or reader.getsampwidth() != 2
                        or not 8000 <= rate <= 48000 or channels not in (1, 2)
                        or not 0 < length <= rate * 600):
                    raise CutdownError("requires 16-bit PCM WAV, mono/stereo, 8–48kHz, at most 600s")
                start, end = _frames(spec.start_ms, rate), _frames(spec.end_ms, rate)
                if not start < end <= length:
                    raise CutdownError("selection exceeds source duration")
                reader.setpos(length - 1)
                if len(reader.readframes(1)) != channels * 2:
                    raise CutdownError("truncated source audio")
                reader.setpos(start)
                raw = reader.readframes(end - start)
                if len(raw) != (end - start) * channels * 2:
                    raise CutdownError("truncated source selection")
            stream.seek(0)
            if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                raise CutdownError("source changed during read")
    except (OSError, wave.Error, EOFError) as exc:
        raise CutdownError("could not read PCM WAV") from exc
    selected = array("h")
    selected.frombytes(raw)
    if sys.byteorder != "little":
        selected.byteswap()
    target = _frames(spec.target_ms, rate)
    overlap = _frames(spec.crossfade_ms, rate)
    if overlap * 2 > end - start:
        raise CutdownError("crossfade exceeds half of rounded selection")
    fade_in, fade_out = _frames(spec.fade_in_ms, rate), _frames(spec.fade_out_ms, rate)
    if fade_in + fade_out > target:
        raise CutdownError("rounded fades overlap")
    output, repeats = _compose(selected, channels, target, overlap)
    _fade(output, channels, target, fade_in, fade_out)
    if sys.byteorder != "little":
        output.byteswap()
    created = False
    try:
        with destination.open("xb") as stream:
            created = True
            with wave.open(stream, "wb") as writer:
                writer.setparams((channels, 2, rate, target, "NONE", "not compressed"))
                writer.writeframes(output.tobytes())
        with destination.open("rb") as stream:
            output_digest = hashlib.file_digest(stream, "sha256").hexdigest()
    except (OSError, wave.Error) as exc:
        if created:
            destination.unlink(missing_ok=True)
        raise CutdownError("could not write soundtrack export") from exc
    return {"operation": "pcm-cutdown-v1", "ai_generation_performed": False,
            "rights_user_attested": True, "source_kind_user_attested": source_kind,
            "source_simulated": True if source_kind == "simulated-fixture" else None,
            "source_sha256": digest, "output_sha256": output_digest,
            "sample_rate": rate, "channels": channels, "source_start_frame": start,
            "source_end_frame": end, "output_frames": target,
            "duration_seconds": target / rate, "repeat_transitions": repeats,
            "crossfade_frames": overlap if repeats else 0,
            "fade_in_frames": fade_in, "fade_out_frames": fade_out}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--start-ms", type=int, default=0)
    parser.add_argument("--end-ms", type=int, required=True)
    parser.add_argument("--target-ms", type=int, required=True)
    parser.add_argument("--crossfade-ms", type=int, default=0)
    parser.add_argument("--fade-in-ms", type=int, default=0)
    parser.add_argument("--fade-out-ms", type=int, default=0)
    parser.add_argument("--source-kind", choices=SOURCE_KINDS, required=True)
    parser.add_argument("--rights-confirmed", action="store_true")
    args = parser.parse_args()
    try:
        spec = EditSpec(args.start_ms, args.end_ms, args.target_ms, args.crossfade_ms,
                        args.fade_in_ms, args.fade_out_ms)
        metadata = edit_wav(args.source, args.destination, spec,
                            rights_confirmed=args.rights_confirmed, source_kind=args.source_kind)
    except CutdownError as exc:
        parser.error(str(exc))
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
