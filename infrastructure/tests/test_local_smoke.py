import argparse
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from infrastructure.local_smoke import clean_env, fixture_env, local_endpoint, port_value, verify_runtime


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

    def test_worker_probe_is_not_disabled(self):
        compose = (Path(__file__).resolve().parents[1] / "compose.smoke.yaml").read_text()
        worker = compose.split("  worker:\n", 1)[1]
        self.assertNotIn("disable: true", worker)
        self.assertIn("select 1 from synora.jobs limit 0", worker)
        self.assertIn("os.access(p, os.W_OK|os.X_OK)", worker)
        self.assertIn("connect_timeout=3", worker)

    def test_runtime_rejects_unhealthy_worker_even_if_running(self):
        def fake_call(args, env, **kwargs):
            if args[-3:-1] == ["ps", "-q"]:
                return SimpleNamespace(stdout=args[-1])
            service = args[-1]
            limit = (512 if service == "api" else 768) * 1024**2
            info = {"State": {"Running": True, "Health": {"Status": "healthy" if service == "api" else "unhealthy"}},
                    "Config": {"User": "10001:10001"},
                    "HostConfig": {"ReadonlyRootfs": True, "Memory": limit, "Privileged": False,
                                   "CapDrop": ["ALL"], "PidsLimit": 128, "NanoCpus": 1000000000}}
            return SimpleNamespace(stdout=json.dumps([info]))
        with patch("infrastructure.local_smoke.call", side_effect=fake_call):
            with self.assertRaisesRegex(ValueError, "policy failed: worker"):
                verify_runtime(["docker"], ["docker", "compose"], {})
