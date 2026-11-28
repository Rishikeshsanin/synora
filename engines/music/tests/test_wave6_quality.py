import hashlib
import math
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import wave

from benchmarks.music.ace_wave6 import verify_stage
from benchmarks.music.wave6_quality import (CASES, QualityError, choose_precision, classify_generation_error,
                                            review_experiment, semantic_status, write_checked_pcm)


class Wave6QualityTests(unittest.TestCase):
    def test_precision_policy(self):
        gib = 1024**3
        self.assertEqual(choose_precision("instrumental", "auto", (7, 5), 15 * gib), "fp16")
        self.assertEqual(choose_precision("vocals", "auto", (7, 5), 15 * gib), "fp32")
        for mode, precision, capability, memory in (("vocals", "bf16", (7, 5), 15),
                ("vocals", "auto", (7, 5), 10), ("instrumental", "auto", (6, 1), 2)):
            with self.assertRaises(QualityError):
                choose_precision(mode, precision, capability, memory * gib)

    def test_controlled_cases_and_review(self):
        self.assertEqual(CASES["telugu-native"][:3], CASES["telugu-roman"][:3])
        self.assertEqual(CASES["hindi-native"][:3], CASES["hindi-roman"][:3])
        self.assertEqual(semantic_status("vocals", {}), "pending_review")
        self.assertEqual(semantic_status("vocals", {"vocals_present": False}), "failed")
        all_true = dict(musical_coherence=True, requested_style=True, vocals_present=True,
                        language_match=True, lyrics_match=True)
        self.assertEqual(semantic_status("vocals", all_true), "passed")
        with self.assertRaises(QualityError):
            semantic_status("vocals", {"lyrics_match": 1})

    def test_pcm_integrity_metrics(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "tone.wav"
            block = [0.2 * math.sin(2 * math.pi * 440 * i / 8000) for i in range(8000)]
            result = write_checked_pcm(path, (block for _ in range(15)), 8000, 1, 120000, 15)
            self.assertEqual(result["semantic_status"], "pending_review")
            self.assertEqual(result["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertAlmostEqual(result["rms_dbfs"], -16.99, places=2)
            with wave.open(str(path), "rb") as audio:
                self.assertEqual(audio.getnframes(), 120000)
            with self.assertRaises(QualityError):
                write_checked_pcm(path, [], 8000, 1, 120000, 15)

    def test_nonfinite_rejected_before_conversion(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.wav"
            for value in (math.nan, math.inf, -math.inf, 1.1):
                with self.subTest(value=value), self.assertRaises(QualityError):
                    write_checked_pcm(path, [[0.2, value]], 8000, 1, 120000, 15)
                self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_silence_clipping_incomplete_and_duration(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.wav"
            for value, count, frames in ((0, 120000, 120000), (1, 120000, 120000),
                                         (0.2, 10, 120000), (0.2, 10, 8000)):
                with self.subTest(value=value, count=count), self.assertRaises(QualityError):
                    write_checked_pcm(path, [[value] * count], 8000, 1, frames, 15)
                self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_numerical_error_classification(self):
        self.assertEqual(classify_generation_error("Generation produced NaN or Inf latents (nan=48000)"),
                         "nonfinite_latents")
        self.assertEqual(classify_generation_error("Generation produced zero latents"), "zero_latents")
        self.assertEqual(classify_generation_error("secret arbitrary message"), "generation_failed")

    def test_reusable_stage_checks_bytes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, snapshot, stage = (root / name for name in ("source", "snapshot", "stage"))
            for directory in (source / "acestep/models", snapshot, stage):
                directory.mkdir(parents=True)
            (source / "acestep/models/model.py").write_text("# pinned model code\n")
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            subprocess.run(["git", "-C", str(source), "add", "acestep/models/model.py"], check=True)
            for directory in (snapshot, stage):
                (directory / "model.safetensors").write_bytes(b"test weights, not real")
                (directory / "model.py").write_text("# snapshot model code\n")
            first = verify_stage(snapshot, stage, source)
            (stage / "model.py").write_text("# pinned model code\n")
            self.assertEqual(first, verify_stage(snapshot, stage, source))
            (stage / "model.safetensors").write_bytes(b"tampered")
            with self.assertRaises(QualityError):
                verify_stage(snapshot, stage, source)

    def test_review_bound_to_artifact_and_separate_from_integrity(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.wav"
            metrics = write_checked_pcm(audio, [[0.2] * 120000], 8000, 1, 120000, 15)
            # Test-only metadata exercises binding; it is not an inference claim.
            (root / "experiment.json").write_text(json.dumps({"status": "technical_pass",
                "technical_status": "passed", "simulated": False, "artifact": "audio.wav",
                "case": "telugu-native", "mode": "vocals", "metrics": metrics}))
            review = {"listened_to_exact_artifact": True, "audio_sha256": metrics["sha256"],
                      "vocals_present": False}
            result = review_experiment(root, review)
            self.assertEqual(result["semantic_status"], "failed")
            self.assertFalse(result["inference_origin_verified"])
            with self.assertRaises(QualityError):
                review_experiment(root, {**review, "audio_sha256": "wrong"})
            audio.write_bytes(audio.read_bytes() + b"x")
            with self.assertRaises(QualityError):
                review_experiment(root, review)
