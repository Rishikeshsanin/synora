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
