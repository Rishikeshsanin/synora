from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from engines.music import (MusicSpec, GenerationContext, FixtureProvider, LyriaProvider,
                           MusicError, registry, fixture_capabilities)


class Wave2Tests(unittest.TestCase):
    def test_api_payload_bounds_and_normalization(self):
        spec = MusicSpec(prompt=" piano ", mode="instrumental", genres=[" pop "],
                         moods=[], instruments=["a" * 64] * 12,
                         duration_seconds=15, bpm=40, lyrics=None, language=" en ")
        self.assertEqual(spec.prompt, "piano")
        self.assertEqual(spec.genres, ("pop",))
        self.assertEqual(len(spec.instruments), 12)
        self.assertIsNone(spec.lyrics)
        self.assertEqual(spec.language, "en")
        for kwargs in ({"instruments": ["x"] * 13}, {"genres": ["x"] * 13},
                       {"moods": ["x"] * 13}, {"genres": ["x" * 65]},
                       {"language": "x" * 33}, {"lyrics": ""}, {"lyrics": "  "},
                       {"mode": "vocals", "lyrics": "  "}):
            with self.assertRaises(ValueError):
                MusicSpec("piano", **kwargs)

    def test_capabilities_are_json_and_honest(self):
        caps = json.loads(json.dumps(fixture_capabilities()))
        self.assertTrue(caps["simulated"])
        for key in ("vocals", "lyrics", "exact_bpm", "genres", "moods", "instruments", "language"):
            self.assertFalse(caps[key])
        self.assertEqual(caps["duration_control"], "exact")

    def test_lease_callback_cleans_partial_artifact(self):
        class LostLease(Exception):
            pass
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = []
            def update(value):
                progress.append(value)
                if value >= 20:
                    raise LostLease()
            with self.assertRaises(LostLease):
                FixtureProvider().generate(MusicSpec("piano", duration_seconds=15),
                                           GenerationContext(root, progress=update))
            self.assertEqual(list(root.iterdir()), [])
            self.assertEqual(progress, sorted(progress))

    def test_production_denies_even_approved_real(self):
        env = {"SYNORA_ENV": "production", "SYNORA_REAL_MUSIC_APPROVED": "1",
               "SYNORA_LYRIA_APPROVED": "1", "GEMINI_API_KEY": "test"}
        self.assertEqual(registry(env), {})
        def forbidden(*args):
            self.fail("network called")
        with TemporaryDirectory() as tmp, self.assertRaises(MusicError):
            LyriaProvider("test", transport=forbidden).generate(
                MusicSpec("piano"), GenerationContext(Path(tmp), production=True,
                                                      allow_real=True, budget_usd=1))

    def test_lyria_records_id_before_invalid_audio(self):
        ids = []
        def transport(*args):
            return b'{"id":"job123","steps":[{"type":"model_output","content":null}]}'
        with TemporaryDirectory() as tmp, self.assertRaises(MusicError):
            LyriaProvider("test", transport=transport).generate(
                MusicSpec("piano"), GenerationContext(Path(tmp), allow_real=True,
                                                      budget_usd=1, upstream_job=ids.append))
        self.assertEqual(ids, ["job123"])
