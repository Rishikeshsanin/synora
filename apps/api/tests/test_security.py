from dataclasses import replace
import time
from uuid import uuid4
import pytest
from synora.config import settings
from synora import storage

def test_production_fixture_forbidden():
    with pytest.raises(ValueError):
        replace(settings,environment="production",provider="fixture")

def test_signature_fencing(monkeypatch):
    monkeypatch.setattr(storage,"settings",replace(settings,signing_key="x"*32))
    asset=uuid4()
    expiry=int(time.time())+60
    sig=storage.signature(asset,expiry,False)
    assert storage.valid_signature(asset,expiry,False,sig)
    assert not storage.valid_signature(uuid4(),expiry,False,sig)
    assert not storage.valid_signature(asset,expiry,True,sig)
    assert not storage.valid_signature(asset,expiry-120,False,sig)

def test_storage_path_rejects_traversal():
    with pytest.raises(ValueError): storage.local_path("../../anything.wav")


def test_malformed_signature(monkeypatch):
    monkeypatch.setattr(storage,"settings",replace(settings,signing_key="x"*32))
    assert not storage.valid_signature(uuid4(),int(time.time())+60,False,"é"*64)

def test_private_file_permissions(tmp_path,monkeypatch):
    import stat
    monkeypatch.setattr(storage,"settings",replace(settings,media_dir=tmp_path))
    key=f"{uuid4()}/{uuid4()}/{uuid4()}.wav"
    storage.put_local(key,b"test")
    assert stat.S_IMODE(storage.local_path(key).stat().st_mode)==0o600
    storage.delete_local(key)
    assert not storage.local_path(key).exists()
