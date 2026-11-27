import hashlib
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
import wave

from engines.music.cutdown import CutdownError, EditSpec, edit_wav


class CutdownTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "original.wav"
        # Original deterministic stereo ramp, not AI music.
        self.samples = [(i % 1000 - 500, 1000 - i % 1000) for i in range(16000)]
        with wave.open(str(self.source), "wb") as out:
            out.setparams((2, 2, 8000, 0, "NONE", "not compressed"))
            out.writeframes(b"".join(struct.pack("<hh", *pair) for pair in self.samples))
        self.original = self.source.read_bytes()

    def edit(self, name, spec, **kwargs):
        return edit_wav(self.source, self.root / name, spec, **({
            "rights_confirmed": True, "source_kind": "simulated-fixture"} | kwargs))

    def read(self, name):
        with wave.open(str(self.root / name), "rb") as stream:
            self.assertEqual(stream.getnchannels(), 2)
            self.assertEqual(stream.getframerate(), 8000)
            return list(struct.iter_unpack("<hh", stream.readframes(stream.getnframes())))

    def test_sample_exact_trim_and_provenance(self):
        metadata = self.edit("cut.wav", EditSpec(125, 1500, 1000))
        self.assertEqual(self.read("cut.wav"), self.samples[1000:9000])
        self.assertEqual(metadata["output_frames"], 8000)
        self.assertEqual(metadata["source_sha256"], hashlib.sha256(self.original).hexdigest())
        self.assertEqual(metadata["output_sha256"], hashlib.sha256((self.root / "cut.wav").read_bytes()).hexdigest())
        self.assertIs(metadata["source_simulated"], True)
        self.assertIs(metadata["ai_generation_performed"], False)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_crossfade_math_stereo_and_exact_target(self):
        metadata = self.edit("loop.wav", EditSpec(0, 1000, 2300, 100))
        samples = self.read("loop.wav")
        self.assertEqual(len(samples), 18400)
        self.assertEqual(samples[:7200], self.samples[:7200])
        for j in (0, 399, 799):
            expected = tuple((self.samples[7200 + j][ch] * (800 - j)
                              + self.samples[j][ch] * (j + 1)) // 801 for ch in (0, 1))
            self.assertEqual(samples[7200 + j], expected)
        self.assertEqual(samples[8000], self.samples[800])
        self.assertEqual(metadata["repeat_transitions"], 2)
        self.assertEqual(metadata["crossfade_frames"], 800)

    def test_endpoint_fades_and_repeat_determinism(self):
        spec = EditSpec(0, 1000, 3000, 50, 100, 100)
        a = self.edit("a.wav", spec)
        b = self.edit("b.wav", spec)
        samples = self.read("a.wav")
        self.assertEqual(samples[0], (0, 0))
        self.assertEqual(samples[-1], (0, 0))
        self.assertEqual(samples[799], self.samples[799])
        self.assertEqual(a["output_sha256"], b["output_sha256"])

    def test_invalid_specs(self):
        for args in ((True, 1000, 1000), (0, 100, 1000), (0, 1000, 999),
                     (0, 1000, 120001), (0, 1000, 2000, 501), (0, 1000, 1000, 1),
                     (0, 1000, 1000, 0, 600, 600), (0, 601000, 1000)):
            with self.subTest(args=args), self.assertRaises(CutdownError):
                EditSpec(*args)

    def test_rights_existing_output_and_truncated_source(self):
        spec = EditSpec(0, 1000, 1000)
        for options in ({"rights_confirmed": False}, {"source_kind": "unknown"}):
            with self.assertRaises(CutdownError):
                self.edit("refused.wav", spec, **options)
            self.assertFalse((self.root / "refused.wav").exists())
        (self.root / "exists.wav").write_bytes(b"keep")
        with self.assertRaises(CutdownError):
            self.edit("exists.wav", spec)
        self.assertEqual((self.root / "exists.wav").read_bytes(), b"keep")
        self.source.write_bytes(self.original[:-4])
        with self.assertRaises(CutdownError):
            self.edit("truncated.wav", spec)
        self.assertFalse((self.root / "truncated.wav").exists())

    def test_invalid_pcm_and_out_of_range(self):
        with self.assertRaises(CutdownError):
            self.edit("invalid.wav", EditSpec(0, 2500, 1000))
        self.source.write_bytes(b"not a wav" * 100)
        with self.assertRaises(CutdownError):
            self.edit("invalid.wav", EditSpec(0, 1000, 1000))
        self.assertFalse((self.root / "invalid.wav").exists())
