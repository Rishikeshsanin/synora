import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from engines.music import AceStepProvider, GenerationContext, LyriaProvider, MusicError, MusicSpec


class ProviderSafetyTests(unittest.TestCase):
    def test_ace_rejects_malformed_result_without_download(self):
        for status, file_url in (
            (True, "/v1/audio?path=x"), (1, None), (1, 17),
            (1, "/v1/audio?path="), (1, "/v1/audio?path=a&path=b"),
            (1, "/v1/audio?path=a&other=b"), (1, "/v1/audio?path=%00"),
            (1, "/v1/audio?path=a\n"), (1, "//external.example/v1/audio?path=a"),
        ):
            with self.subTest(status=status, file_url=file_url), TemporaryDirectory() as tmp:
                upstream = []

                def transport(url, headers, payload, timeout, limit):
                    if url.endswith("/release_task"):
                        data = {"task_id": "abc"}
                    elif url.endswith("/query_result"):
                        data = [{"task_id": "abc", "status": status, "result": [
                            {"file": file_url, "dit_model": "acestep-v15-turbo"}]}]
                    else:
                        self.fail("unexpected download")
                    return json.dumps({"code": 200, "data": data}).encode()

                provider = AceStepProvider("http://localhost:8001", "test", 0.1, transport)
                with self.assertRaises(MusicError):
                    provider.generate(MusicSpec("piano"), GenerationContext(
                        Path(tmp), allow_real=True, budget_usd=0.1, upstream_job=upstream.append))
                self.assertEqual(upstream, ["abc"])
                self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_lyria_preserves_upstream_id_for_terminal_or_incomplete_response(self):
        for status in ("failed", "cancelled", "requires_action", "in_progress"):
            with self.subTest(status=status), TemporaryDirectory() as tmp:
                upstream = []

                def transport(*args):
                    return json.dumps({"id": "abc", "status": status}).encode()

                with self.assertRaises(MusicError):
                    LyriaProvider("test", transport=transport).generate(
                        MusicSpec("piano"), GenerationContext(Path(tmp), allow_real=True,
                            budget_usd=1, upstream_job=upstream.append))
                self.assertEqual(upstream, ["abc"])
                self.assertEqual(list(Path(tmp).iterdir()), [])
