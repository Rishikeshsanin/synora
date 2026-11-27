"""Independent filesystem exercise of the actual reconciler with controlled DB responses.

This does not prove PostgreSQL locking; test_wave2_worker.py is the live DB gate.
"""
import importlib.util
import sys
import types
import os
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
import pytest


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    pkg = types.ModuleType("qa_fixture")
    pkg.__path__ = []
    db = types.ModuleType("qa_fixture.db")
    cfg = types.ModuleType("qa_fixture.config")
    storage = types.ModuleType("qa_fixture.storage")
    cfg.settings = types.SimpleNamespace(environment="test", provider="fixture", media_dir=tmp_path)
    storage.local_path = lambda key: tmp_path / key
    owner, job, token = uuid4(), uuid4(), uuid4()
    key = f"{owner}/{job}/{token}.wav"
    path = storage.local_path(key)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"test")
    os.utime(path, (time.time() - 700,) * 2)
    state = {"row": {"status": "queued", "lease_token": None}, "asset": None, "down": False}

    class Conn:
        def execute(self, sql, args):
            if "for update" in sql:
                return types.SimpleNamespace(fetchone=lambda: state["row"])
            assert "storage_key" in sql
            return types.SimpleNamespace(fetchone=lambda: state["asset"])

    @contextmanager
    def connect():
        if state["down"]:
            raise ConnectionError("injected")
        yield Conn()

    db.db = connect
    for module in (pkg, db, cfg, storage):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    source = Path(__file__).resolve().parents[2] / "apps/api/synora/cleanup.py"
    spec = importlib.util.spec_from_file_location("qa_fixture.cleanup", source)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, key, path, token, state, cfg.settings


@pytest.mark.parametrize("mode", ["young", "active", "referenced", "unknown", "down", "production", "grace", "orphan"])
def test_actual_cleanup(fixture, mode):
    mod, key, path, token, state, settings = fixture
    if mode == "young":
        os.utime(path, None)
    elif mode == "active":
        state["row"] = {"status": "running", "lease_token": token}
    elif mode == "referenced":
        state["asset"] = {"exists": True}
    elif mode == "unknown":
        state["row"] = None
    elif mode == "down":
        state["down"] = True
        with pytest.raises(ConnectionError):
            mod.reconcile_attempt(key)
        assert path.is_file()
        return
    elif mode == "production":
        settings.environment = "production"
        with pytest.raises(RuntimeError):
            mod.reconcile_attempt(key)
        assert path.is_file()
        return
    elif mode == "grace":
        with pytest.raises(ValueError):
            mod.reconcile_attempt(key, 599)
        assert path.is_file()
        return
    elif mode == "orphan":
        assert mod.reconcile_attempt(key)
        assert not path.exists()
        assert not mod.reconcile_attempt(key)
        return
    assert mod.reconcile_attempt(key) is False
    assert path.is_file()
