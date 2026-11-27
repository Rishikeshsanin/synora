import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from engines.music import (MusicSpec, GenerationContext, FixtureProvider, AceStepProvider,
                           LyriaProvider, MusicError, registry)
from engines.music.audio import inspect_audio, master

def envelope(data):
    return json.dumps({"code":200,"error":None,"data":data}).encode()

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.spec = MusicSpec("original piano piece", duration_seconds=15, bpm=100)

    def ctx(self, name, **kwargs):
        return GenerationContext(self.root / name, **kwargs)

    def test_validation(self):
        for kwargs in ({"duration_seconds":14},{"bpm":True},{"lyrics":"not instrumental"},{"genres":"pop"},
                       {"mode":"bad"},{"duration_seconds":121}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                MusicSpec("test",**kwargs)

    def test_fixture_deterministic_and_labeled(self):
        provider = FixtureProvider()
        a = provider.generate(self.spec,self.ctx("a"))
        b = provider.generate(self.spec,self.ctx("b"))
        self.assertEqual(a.metrics["sha256"],b.metrics["sha256"])
        self.assertEqual(a.actual_duration_seconds,15)
        self.assertTrue(a.simulated)
        self.assertEqual(a.estimated_cost_usd,0)
        self.assertEqual(a.mime_type,"audio/wav")

    def test_fixture_production_and_cancel(self):
        with self.assertRaises(MusicError):
            FixtureProvider().generate(self.spec,self.ctx("p",production=True))
        with self.assertRaises(MusicError):
            FixtureProvider().generate(self.spec,self.ctx("c",cancelled=lambda:True))
        self.assertFalse((self.root/"p").exists())
        self.assertFalse((self.root/"c").exists())

    def test_registry_fails_closed(self):
        self.assertEqual(set(registry({})),{"fixture"})
        self.assertEqual(registry({"SYNORA_ENV":"production"}),{})
        with self.assertRaises(MusicError):
            registry({"SYNORA_REAL_MUSIC_APPROVED":"1","SYNORA_ACE_APPROVED":"1"})

    def test_budget_prevents_network(self):
        def forbidden(*args):
            self.fail("network must not be invoked")
        lyria=LyriaProvider("test",transport=forbidden)
        for ctx in (self.ctx("a"),self.ctx("b",allow_real=True,budget_usd=0.01)):
            with self.assertRaises(MusicError):
                lyria.generate(self.spec,ctx)
        with self.assertRaises(MusicError):
            LyriaProvider("test",model="lyria-3-clip-preview",transport=forbidden).generate(
                self.spec,self.ctx("c",allow_real=True,budget_usd=1))

    def test_ace_protocol(self):
        wav=FixtureProvider().generate(self.spec,self.ctx("fixture")).artifact.read_bytes()
        calls=[]
        upstream=[]
        def transport(url, headers, payload, timeout, limit):
            calls.append(url)
            if url.endswith("/release_task"):
                self.assertEqual(payload["batch_size"],1)
                self.assertEqual(payload["lyrics"],"[Instrumental]")
                self.assertEqual(payload["bpm"],100)
                return envelope({"task_id":"abc"})
            if url.endswith("/query_result"):
                self.assertEqual(payload,{"task_id_list":["abc"]})
                return envelope([{"task_id":"abc","status":1,"result":json.dumps([
                    {"file":"/v1/audio?path=%2Ftest.wav","dit_model":"acestep-v15-turbo"}])}])
            self.assertIn("/v1/audio?path=",url)
            return wav
        out=AceStepProvider("http://localhost:8001","test",0.10,transport).generate(
            self.spec,self.ctx("ace",allow_real=True,budget_usd=0.10,upstream_job=upstream.append))
        self.assertFalse(out.simulated) # protocol test transport is mocked; no actual AI inference
        self.assertEqual(out.actual_duration_seconds,15)
        self.assertEqual(upstream,["abc"])
        self.assertEqual(len(calls),3)
        self.assertFalse(out.provenance["revision_verified_by_api"])

    def test_ace_rejects_external_audio_and_wrong_model(self):
        for file, model in (("https://attacker.example/v1/audio?path=x","acestep-v15-turbo"),
                            ("/v1/audio?path=x","different")):
            def transport(url, headers, payload, timeout, limit):
                if url.endswith("/release_task"):
                    return envelope({"task_id":"abc"})
                if url.endswith("/query_result"):
                    return envelope([{"task_id":"abc","status":1,"result":[{"file":file,"dit_model":model}]}])
                self.fail("must not download")
            with self.assertRaises(MusicError):
                AceStepProvider("http://localhost:8001","test",0.1,transport).generate(
                    self.spec,self.ctx("ace",allow_real=True,budget_usd=0.1))

    def test_lyria_protocol(self):
        # Mock response containing actual local fixture WAV bytes; not AI music.
        wav=FixtureProvider().generate(self.spec,self.ctx("fixture")).artifact.read_bytes()
        def transport(url, headers, payload, timeout, limit):
            self.assertEqual(payload["model"],"lyria-3.5")
            self.assertIn("Target duration: 15",payload["input"])
            self.assertIn("Api-Revision",headers)
            return json.dumps({"steps":[{"type":"model_output","content":[
                {"type":"audio","data":base64.b64encode(wav).decode()}]}]}).encode()
        out=LyriaProvider("test",transport=transport).generate(
            self.spec,self.ctx("lyria",allow_real=True,budget_usd=0.08))
        self.assertEqual(out.actual_duration_seconds,15)
        self.assertEqual(out.estimated_cost_usd,0.08)
        self.assertFalse(out.provenance["seed_supported"])

    def test_audio_invalid_and_master(self):
        bad=self.root/"bad.wav"
        bad.write_bytes(b"not an audio file"*20)
        with self.assertRaises(MusicError):
            inspect_audio(bad)
        out=FixtureProvider().generate(self.spec,self.ctx("fixture"))
        normalized=master(out.artifact,self.root/"master.wav")
        self.assertAlmostEqual(normalized["duration_seconds"],15,places=2)
        self.assertEqual(normalized["sample_rate"],44100)

if __name__ == "__main__":
    unittest.main()
