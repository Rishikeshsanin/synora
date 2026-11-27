import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / "ci" / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


evidence = load("ci_evidence", "evidence.py")
fixture = load("ci_fixture_validator", "validate-browser-fixture.py")


class EvidenceTests(unittest.TestCase):
    def test_counts_only_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.xml"
            path.write_text('<testsuite><testcase name="SECRET"/><testcase><failure>SECRET</failure></testcase><testcase><error>SECRET</error></testcase><testcase><skipped>SECRET</skipped></testcase></testsuite>')
            result = evidence.junit_summary([path, Path(tmp) / "missing.xml"])
            self.assertEqual(result[0], dict(suite="test", status="executed", total=4,
                                             passed=1, failed=1, errors=1, skipped=1))
            self.assertEqual(result[1]["status"], "not_run")
            self.assertNotIn("SECRET", json.dumps(result))

    def test_two_private_matched_sessions_and_reject_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.json", Path(tmp) / "b.json"
            web = "http://127.0.0.1:3000"
            for path, token in [(a, "token-a"), (b, "token-b")]:
                path.write_text(json.dumps({"origins": [{"origin": web, "localStorage": [
                    {"name": "sb-127-auth-token", "value": json.dumps({"access_token": token})}]}]}))
                os.chmod(path, 0o600)
            env = dict(RUNNER_TEMP=tmp, SYNORA_QA_TOKEN_A="token-a", SYNORA_QA_TOKEN_B="token-b",
                       FIXTURE_TOKENS_JSON=json.dumps({"token-a": "11111111-1111-4111-8111-111111111111",
                                                       "token-b": "22222222-2222-4222-8222-222222222222"}),
                       SYNORA_QA_STORAGE_STATE=str(a), SYNORA_QA_STORAGE_STATE_B=str(b),
                       SYNORA_QA_FIXTURE_PAGE_URL=web + "/studio",
                       SYNORA_QA_FIXTURE_JOB_ID="33333333-3333-4333-8333-333333333333",
                       SYNORA_QA_API_URL="http://127.0.0.1:8000", SYNORA_QA_WEB_URL=web)
            self.assertTrue(fixture.validate(env))
            with self.assertRaises(ValueError):
                fixture.validate(env | {"SYNORA_QA_STORAGE_STATE_B": str(a)})
            with self.assertRaises(ValueError):
                fixture.validate(env | {"SYNORA_QA_WEB_URL": "https://example.com"})
            with self.assertRaises(ValueError):
                fixture.validate(env | {"SYNORA_QA_TOKEN_B": "token-a"})
            os.chmod(b, 0o644)
            with self.assertRaises(ValueError):
                fixture.validate(env)


if __name__ == "__main__":
    unittest.main()
