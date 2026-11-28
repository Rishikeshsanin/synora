import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from infrastructure.gpu_host import (Blocked, offline_env, private_dir, run_bounded,
                                     session_lease, verify_audit, save_inventory, memory_gate, inventory)


@unittest.skipUnless(os.name == "posix", "POSIX research host required")
class GPUHostTests(unittest.TestCase):
    def test_private_workspace_and_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = private_dir(Path(tmp))
            env = offline_env({"PATH": "/usr/bin", "HF_TOKEN": "private",
                               "AWS_SECRET_ACCESS_KEY": "private", "HTTP_PROXY": "private",
                               "PYTHONPATH": "unexpected", "CUDA_VISIBLE_DEVICES": "7"}, root, "0")
            self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "0")
            self.assertEqual(env["HF_HUB_OFFLINE"], "1")
            for key in ("HF_TOKEN", "AWS_SECRET_ACCESS_KEY", "HTTP_PROXY", "PYTHONPATH"):
                self.assertNotIn(key, env)
            (root / "bad").symlink_to(root / "home", target_is_directory=True)
            with self.assertRaises(Blocked):
                private_dir(root / "bad")
            root.chmod(0o755)
            with self.assertRaises(Blocked):
                private_dir(root)
            root.chmod(0o700)

    def test_audit_complete_and_fail_closed(self):
        installed = {"torch": {"version": "2.10.0+cu128"},
                     "ace-step": {"version": "1.5.0"}}
        valid = {"dependencies": [
            {"name": "torch", "version": "2.10.0+cu128", "vulns": []},
            {"name": "ace-step", "skip_reason": "local source"}]}
        self.assertEqual(verify_audit(valid, installed, {"ace-step": "1.5.0"})["audited_packages"], 2)
        with self.assertRaises(Blocked):
            verify_audit(valid, installed, {})
        for deps in (
            valid["dependencies"][1:],
            [{"name": "torch", "version": "2.10.0", "vulns": []}, valid["dependencies"][1]],
            [{"name": "torch", "version": "2.10.0+cu128", "vulns": [{"id": "test"}]}, valid["dependencies"][1]],
            [{"name": "torch", "skip_reason": "unknown"}, valid["dependencies"][1]],
        ):
            with self.assertRaises(Blocked):
                verify_audit({"dependencies": deps}, installed, {"ace-step": "1.5.0"})

    def test_exclusive_session_and_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with session_lease(root):
                with self.assertRaises(Blocked):
                    with session_lease(root):
                        self.fail("duplicate session admitted")
            self.assertFalse((root / "session.lock").exists())
            with session_lease(root):
                self.assertTrue((root / "session.lock").exists())

    def test_actual_process_completion_and_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = offline_env(os.environ, root)
            result = run_bounded([sys.executable, "-c", "print('not forwarded')"], env, root, 3)
            self.assertEqual(result["status"], "completed")
            with self.assertRaises(Blocked):
                run_bounded([sys.executable, "-c", "import time; time.sleep(20)"], env, root, 1)
            self.assertFalse((root / "session.lock").exists())
            with self.assertRaises(Blocked):
                run_bounded([sys.executable, "-c", "raise SystemExit(3)"], env, root, 3)
            self.assertFalse((root / "session.lock").exists())

    def test_private_inventory_reuse_and_change_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            installed = {"torch": {"version": "2.10.0", "license": "BSD"}}
            save_inventory(root, installed)
            save_inventory(root, installed)
            self.assertEqual(json.loads((root / "inventory.json").read_text()), installed)
            with self.assertRaises(Blocked):
                save_inventory(root, {"torch": {"version": "2.11.0"}})
            (root / "inventory.json").chmod(0o644)
            with self.assertRaises(Blocked):
                save_inventory(root, installed)

    def test_conservative_hardware_policy(self):
        memory_gate(15360, 12000, 15000)
        for total, free, available in ((2048, 2048, 16000), (15360, 9000, 16000),
                                       (15360, 12000, 8000)):
            with self.assertRaises(Blocked):
                memory_gate(total, free, available)

    def test_inventory_requires_pinned_checkout_and_virtualenv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "ace"
            python = root / "python"
            python.touch()
            base = {"python": [3, 12], "prefix": str(source / ".venv"), "base_prefix": "/usr",
                    "ace_origin": str(source / "acestep/__init__.py"),
                    "packages": [{"name": "torch", "version": "2.10.0", "license": "BSD"},
                                 {"name": "ace-step", "version": "1.5.0", "license": "MIT"}]}
            with patch("infrastructure.gpu_host.capture", return_value=json.dumps(base)):
                entries, digest = inventory(python, source, {}, root)
                self.assertEqual(len(entries), 2)
                self.assertEqual(len(digest), 64)
            for bad in (dict(base, prefix="/usr"), dict(base, ace_origin="/other/acestep/__init__.py")):
                with patch("infrastructure.gpu_host.capture", return_value=json.dumps(bad)):
                    with self.assertRaises(Blocked):
                        inventory(python, source, {}, root)
