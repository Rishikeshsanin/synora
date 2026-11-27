"""Synthetic inputs exercise the evidence verifier; never claim actual inference."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from benchmarks.music.ace_evidence import verify
from engines.music import FixtureProvider, GenerationContext, MusicSpec
from engines.music.providers import ACE_CODE, ACE_REVISION


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        out = FixtureProvider().generate(MusicSpec("test", duration_seconds=15),
                                         GenerationContext(self.root / "audio"))
        self.path = out.artifact
        # Test-only fabricated manifest to test integrity, never inference evidence.
        self.data = {"status": "succeeded", "simulated": False, "model": "acestep-v15-turbo",
                     "configured_snapshot_revision": ACE_REVISION, "upstream_code_revision": ACE_CODE,
                     "weight_hashes": {"test": "a" * 64}, "initialization_seconds": 1,
                     "generation_seconds": 1, "gpu_total_bytes": 100,
                     "generation_peak_allocated_bytes": 50, "generation_peak_reserved_bytes": 80,
                     "artifact": "audio/fixture.wav", "duration_requested_seconds": 15,
                     "metrics": out.metrics}

    def write(self):
        (self.root / "experiment.json").write_text(json.dumps(self.data))

    def test_consistency_is_not_origin_attestation(self):
        self.write()
        report = verify(self.root)
        self.assertEqual(report["artifact_integrity"], "passed")
        self.assertFalse(report["inference_origin_verified"])
        self.assertFalse(report["quality_verified"])
        self.assertEqual(report["duration_error_seconds"], 0)

    def test_simulated_or_failed_rejected(self):
        for changes in ({"simulated": True}, {"status": "failed"}, {"weight_hashes": {}},
                        {"gpu_total_bytes": 10}, {"upstream_code_revision": "wrong"},
                        {"artifact": "../fixture.wav"}):
            with self.subTest(changes=changes):
                original = self.data.copy()
                self.data.update(changes)
                self.write()
                with self.assertRaises(ValueError):
                    verify(self.root)
                self.data = original

    def test_tampering_rejected(self):
        self.write()
        self.path.write_bytes(self.path.read_bytes() + b"changed")
        with self.assertRaises(ValueError):
            verify(self.root)
