import json
import unittest
from pathlib import Path
from infrastructure.budget import Admission

ROOT = Path(__file__).resolve().parents[1]

class PolicyTests(unittest.TestCase):
    def test_default_denies(self):
        self.assertFalse(Admission().allows(estimate=1, spent=0, reserved=0, active=0))

    def test_policy_defaults(self):
        config = json.loads((ROOT / "policy.json").read_text())
        self.assertIs(config["real_generation_enabled"], False)
        for key in ("monthly_budget_microusd", "max_job_microusd", "max_concurrent_gpu_jobs"):
            self.assertEqual(config[key], 0)
        self.assertLessEqual(config["max_duration_seconds"], 120)
        self.assertLessEqual(config["signed_url_ttl_seconds"], 300)

    def test_exact_boundary_and_overage(self):
        p = Admission(True, 100, 30, 2)
        self.assertTrue(p.allows(estimate=30, spent=40, reserved=30, active=1))
        self.assertFalse(p.allows(estimate=30, spent=41, reserved=30, active=1))
        self.assertFalse(p.allows(estimate=31, spent=0, reserved=0, active=0))

    def test_concurrency_and_invalid_input(self):
        p = Admission(True, 100, 30, 2)
        for estimate, spent, reserved, active in [(1,0,0,2), (0,0,0,0), (-1,0,0,0), (1,-1,0,0), (1,0,-1,0), (True,0,0,0), (1,0,0,-1)]:
            with self.subTest(estimate=estimate, spent=spent, reserved=reserved, active=active):
                self.assertFalse(p.allows(estimate=estimate, spent=spent, reserved=reserved, active=active))

    def test_deploy_proposals_disabled(self):
        vercel = json.loads((ROOT / "deploy/vercel.example.json").read_text())
        self.assertIs(vercel["git"]["deploymentEnabled"], False)
        render = (ROOT / "deploy/render.staging.yaml").read_text()
        self.assertIn("autoDeployTrigger: off", render)
        self.assertIn('value: "false"', render)
        self.assertIn('value: "0"', render)
        self.assertNotIn("type: worker", render)
        self.assertIn("127.0.0.1:55432:5432", (ROOT / "compose.yaml").read_text())

if __name__ == "__main__":
    unittest.main()
