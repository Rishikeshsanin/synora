"""CPU-only independent research evidence checks; never attest inference origin."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import tempfile
import unittest
import wave

MAX_BYTES = 80 * 1024 * 1024
ACE_REVISION = "eb84216a8ece2d56388e401efc28061a0c30a209"
ACE_CODE = "ca1e85fe9430179831e6bc6be790c332190a3866"
HEX = re.compile(r"[0-9a-f]{64}")


def audio_metrics(path, target):
    """Bounded PCM analysis, 100 ms RMS windows; not a musical quality score."""
    if type(target) is not int or not 15 <= target <= 120:
        raise ValueError("unsupported target duration")
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not 44 <= path.stat().st_size <= MAX_BYTES:
        raise ValueError("invalid artifact")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    size = path.stat().st_size
    try:
        with wave.open(str(path), "rb") as wav:
            rate, channels, width, frames = (wav.getframerate(), wav.getnchannels(),
                                              wav.getsampwidth(), wav.getnframes())
            if not (8000 <= rate <= 192000 and channels in (1, 2) and width in (2, 3, 4)
                    and 0 < frames <= 125 * rate):
                raise ValueError("unsupported PCM metadata")
            scale = 1 << (8 * width - 1)
            remaining = frames
            peak = clipped = tail = quiet = total = 0
            while remaining:
                count = min(remaining, rate // 10)
                block = wav.readframes(count)
                if len(block) != count * channels * width:
                    raise ValueError("truncated PCM")
                if width == 3:
                    samples = (int.from_bytes(block[i:i+3], "little", signed=True)
                               for i in range(0, len(block), 3))
                else:
                    samples = (s[0] for s in struct.iter_unpack("<h" if width == 2 else "<i", block))
                energy = 0
                for sample in samples:
                    absolute = abs(sample)
                    peak = max(peak, absolute)
                    clipped += absolute >= scale - 1
                    energy += sample * sample
                total += count * channels
                silent = energy <= count * channels * (scale * 0.01) ** 2
                quiet += count if silent else 0
                tail = tail + count if silent else 0
                remaining -= count
    except (wave.Error, EOFError) as exc:
        raise ValueError("unsupported or malformed PCM WAV") from exc
    duration = frames / rate
    flags = []
    if abs(duration - target) > 0.5:
        flags.append("duration_mismatch")
    if quiet / frames >= 0.95:
        flags.append("mostly_silent")
    if tail / rate >= 2:
        flags.append("silent_tail")
    if clipped / total >= 0.001:
        flags.append("sample_clipping")
    return {"sha256": digest, "bytes": size, "sample_rate": rate, "channels": channels,
            "duration_seconds": duration, "peak_fraction": peak / scale,
            "clipped_sample_fraction": clipped / total, "quiet_frame_fraction": quiet / frames,
            "silent_tail_seconds": tail / rate, "technical_flags": flags}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate manifest key")
        result[key] = value
    return result


def _nonfinite(_value):
    raise ValueError("nonfinite manifest value")


def verify_experiment(directory):
    root = Path(directory).resolve(strict=True)
    manifest = root / "experiment.json"
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > 1024 * 1024:
        raise ValueError("invalid manifest")
    data = json.loads(manifest.read_text(encoding="utf-8"), object_pairs_hook=_unique,
                      parse_constant=_nonfinite)
    if not isinstance(data, dict):
        raise ValueError("invalid manifest object")
    if data.get("status") != "succeeded" or data.get("simulated") is not False:
        raise ValueError("not a successful non-fixture experiment")
    if (data.get("model") != "acestep-v15-turbo" or
            data.get("configured_snapshot_revision") != ACE_REVISION or
            data.get("upstream_code_revision") != ACE_CODE):
        raise ValueError("unpinned experiment identity")
    hashes = data.get("weight_hashes")
    if not isinstance(hashes, dict) or not hashes or any(
            not isinstance(v, str) or not HEX.fullmatch(v) for v in hashes.values()):
        raise ValueError("invalid weight digest declarations")
    for key in ("initialization_seconds", "generation_seconds", "gpu_total_bytes",
                "generation_peak_allocated_bytes", "generation_peak_reserved_bytes"):
        value = data.get(key)
        if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
            raise ValueError("invalid telemetry")
    if not data["generation_peak_allocated_bytes"] <= data["generation_peak_reserved_bytes"] <= data["gpu_total_bytes"]:
        raise ValueError("inconsistent memory telemetry")
    if any(data.get(k) is not None for k in ("quality_score", "prompt_adherence_score")):
        raise ValueError("self-reported quality score is not independent evidence")
    relative = data.get("artifact")
    if not isinstance(relative, str):
        raise ValueError("missing artifact")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or len(path.parts) < 2 or path.parts[0] != "audio":
        raise ValueError("unsafe artifact path")
    cursor = root
    for part in path.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("symlink artifact path")
    actual = audio_metrics(cursor, data.get("duration_requested_seconds"))
    recorded = data.get("metrics")
    if not isinstance(recorded, dict) or recorded.get("mime_type") != "audio/wav":
        raise ValueError("missing recorded WAV metadata")
    for key in ("sha256", "bytes", "sample_rate", "channels"):
        if actual[key] != recorded.get(key):
            raise ValueError("artifact metadata mismatch: " + key)
    duration = recorded.get("duration_seconds")
    if type(duration) not in (float, int) or not math.isfinite(duration) or abs(duration-actual["duration_seconds"]) > 0.01:
        raise ValueError("recorded duration mismatch")
    return {"artifact_integrity": "passed", "technical_gate": "review_required" if actual["technical_flags"] else "passed",
            "metrics": actual, "inference_origin_verified": False, "weight_bytes_verified": False,
            "vocal_lyrics_language_adherence": "unverified", "commercial_license_verified": False,
            "release_approved": False}


class AudioQualityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "audio").mkdir()
        self.path = self.root / "audio" / "test.wav"

    def make(self, seconds=15, tail=0, clip=False, silent=False):
        # Original synthetic QA signal only. Never a real model result.
        rate = 8000
        value = 0 if silent else 32767 if clip else 4000
        tone = struct.pack("<hh", value, -value) * (rate // 2)
        with wave.open(str(self.path), "wb") as wav:
            wav.setparams((1, 2, rate, 0, "NONE", "not compressed"))
            for i in range(seconds):
                wav.writeframes(tone if i < seconds-tail else b"\0" * rate * 2)

    def manifest(self, seconds=15):
        self.make(seconds)
        actual = audio_metrics(self.path, seconds)
        return {"status": "succeeded", "simulated": False, "model": "acestep-v15-turbo",
                "configured_snapshot_revision": ACE_REVISION, "upstream_code_revision": ACE_CODE,
                "weight_hashes": {"test-only": "a" * 64}, "initialization_seconds": 1,
                "generation_seconds": 1, "gpu_total_bytes": 100, "generation_peak_allocated_bytes": 30,
                "generation_peak_reserved_bytes": 50, "duration_requested_seconds": seconds,
                "artifact": "audio/test.wav", "metrics": actual | {"mime_type": "audio/wav"}}

    def write(self, data):
        (self.root / "experiment.json").write_text(json.dumps(data))

    def test_technical_flags(self):
        for kwargs, expected in (({}, []), ({"tail": 3}, ["silent_tail"]),
                                 ({"clip": True}, ["sample_clipping"]),
                                 ({"silent": True}, ["mostly_silent", "silent_tail"]),
                                 ({"seconds": 14}, ["duration_mismatch"])):
            with self.subTest(kwargs=kwargs):
                self.make(**kwargs)
                self.assertEqual(audio_metrics(self.path, 15)["technical_flags"], expected)

    def test_truncated_wav(self):
        self.make()
        self.path.write_bytes(self.path.read_bytes()[:-4])
        with self.assertRaises(ValueError):
            audio_metrics(self.path, 15)

    def test_15_30_60_second_consistency_not_quality(self):
        for seconds in (15, 30, 60):
            self.write(self.manifest(seconds))
            report = verify_experiment(self.root)
            self.assertEqual(report["technical_gate"], "passed")
            self.assertFalse(report["inference_origin_verified"])
            self.assertFalse(report["weight_bytes_verified"])
            self.assertFalse(report["release_approved"])
            self.assertEqual(report["vocal_lyrics_language_adherence"], "unverified")

    def test_semantic_quality_score_rejected(self):
        data = self.manifest()
        for changes in ({"simulated": True}, {"status": "failed"}, {"status": "cancelled"},
                        {"quality_score": 100}, {"prompt_adherence_score": 1},
                        {"generation_seconds": float("nan")}, {"gpu_total_bytes": 1},
                        {"upstream_code_revision": "wrong"}, {"weight_hashes": {}},
                        {"artifact": "../test.wav"}):
            with self.subTest(changes=changes):
                self.write(data | changes)
                with self.assertRaises(ValueError):
                    verify_experiment(self.root)

    def test_hash_mismatch(self):
        self.write(self.manifest())
        self.path.write_bytes(self.path.read_bytes() + b"changed")
        with self.assertRaises(ValueError):
            verify_experiment(self.root)

    def test_duplicate_manifest_key(self):
        data = self.manifest()
        (self.root / "experiment.json").write_text(json.dumps(data)[:-1] + ',"status":"succeeded"}')
        with self.assertRaises(ValueError):
            verify_experiment(self.root)

    def test_symlink_artifact(self):
        data = self.manifest()
        self.path.rename(self.root / "outside.wav")
        self.path.symlink_to(self.root / "outside.wav")
        self.write(data)
        with self.assertRaises(ValueError):
            verify_experiment(self.root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", type=Path, required=True)
    args = parser.parse_args()
    result = verify_experiment(args.verify)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["technical_gate"] == "passed" else 2)
