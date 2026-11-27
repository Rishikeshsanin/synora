import argparse
import json
import unittest
from infrastructure.local_smoke import clean_env, fixture_env, local_endpoint, port_value


class LocalSmokeTests(unittest.TestCase):
    def test_local_context_only(self):
        for endpoint in ("unix:///var/run/docker.sock", "npipe:////./pipe/docker_engine"):
            self.assertTrue(local_endpoint(endpoint))
        for endpoint in ("ssh://host", "tcp://127.0.0.1:2375", "https://host", "", None):
            self.assertFalse(local_endpoint(endpoint))

    def test_environment_allowlist(self):
        original = {"PATH": "/bin", "HOME": "/home/test", "DATABASE_URL": "secret",
                    "DOCKER_HOST": "ssh://host", "COMPOSE_PROJECT_NAME": "unrelated",
                    "SUPABASE_SERVICE_ROLE_KEY": "secret", "SYNORA_SMOKE_PASSWORD": "secret",
                    "AWS_ACCESS_KEY_ID": "secret", "HTTP_PROXY": "secret"}
        self.assertEqual(clean_env(original), {"PATH": "/bin", "HOME": "/home/test"})

    def test_random_ephemeral_credentials(self):
        env, a, b = fixture_env({}, "synora-smoke-test", 18081)
        second, c, d = fixture_env({}, "synora-smoke-test", 18081)
        self.assertEqual(len({a, b, c, d}), 4)
        self.assertNotEqual(env["SYNORA_SMOKE_PASSWORD"], second["SYNORA_SMOKE_PASSWORD"])
        self.assertEqual(len(set(json.loads(env["SYNORA_SMOKE_TOKENS"]).values())), 2)
        self.assertEqual(env["SYNORA_SMOKE_IMAGE"], "synora-smoke-test:local")

    def test_port_bounds(self):
        self.assertEqual(port_value("18081"), 18081)
        for value in ("0", "65536", "abc", "127.0.0.1:8000"):
            with self.assertRaises(argparse.ArgumentTypeError):
                port_value(value)
