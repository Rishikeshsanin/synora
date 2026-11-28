"""Local ACE policy tests. No model or network calls."""
from dataclasses import replace
from uuid import uuid4

import pytest
from engines.music.core import GenerationContext, MusicError
from engines.music.providers import AceStepProvider, FixtureProvider
from synora.config import Settings, ACE_WEIGHTS, ACE_CODE
from synora import local_ace
from synora.models import MusicSpec


def local_config(**overrides):
    values=dict(environment="local",provider="ace-step",
                database_url="postgresql://127.0.0.1:55432/synora_dev",
                supabase_url="http://127.0.0.1:54321",supabase_key=str(uuid4()),
                public_url="http://127.0.0.1:8000",signing_key=uuid4().hex,
                fixture_tokens="{}",storage_key="",real_approved=True,ace_local_approved=True,
                ace_license_reviewed=True,ace_url="http://127.0.0.1:8765",ace_key=str(uuid4()),
                ace_weights_revision=ACE_WEIGHTS,ace_code_revision=ACE_CODE,
                ace_precision="fp32",ace_cpu_offload=True)
    return Settings(**(values|overrides))


@pytest.mark.parametrize("change",[
    {"environment":"production"},{"environment":"test"},{"real_approved":False},
    {"ace_local_approved":False},{"ace_license_reviewed":False},
    {"ace_url":"https://example.invalid"},{"ace_url":"http://127.0.0.1:8765@evil.invalid"},
    {"ace_url":"http://127.0.0.1:8765/path"},{"ace_url":"http://localhost:8765"},
    {"ace_url":"http://127.0.0.1:0"},{"public_url":"https://example.invalid"},
    {"supabase_url":"https://example.invalid"},{"fixture_tokens":"{\"invalid\":\"invalid\"}"},
    {"database_url":"postgresql://example.invalid/synora_dev"},
    {"database_url":"postgresql://127.0.0.1:5432/shared"},
    {"database_url":"postgresql://127.0.0.1:5432/synora_dev?host=example.invalid"},
    {"ace_weights_revision":"wrong"},{"ace_code_revision":"wrong"},{"ace_precision":"auto"},
    {"ace_cpu_offload":False},{"storage_key":"not-a-real-key"},
])
def test_local_ace_config_fails_closed(change):
    with pytest.raises(ValueError):
        local_config(**change)


def test_local_free_policy_does_not_weaken_shared_budget_gate(tmp_path):
    cfg=local_config()
    cap=AceStepProvider.capabilities
    regular=GenerationContext(output_dir=tmp_path/"regular",allow_real=True,budget_usd=0)
    with pytest.raises(MusicError):
        regular.authorize(cap,0)
    ctx=local_ace.LocalAceContext(output_dir=tmp_path/"ace",allow_real=True,budget_usd=0,config=cfg)
    ctx.authorize(cap,0)
    assert ctx.output_dir.is_dir()
    for other, estimate in [(FixtureProvider.capabilities,0),(cap,0.01)]:
        with pytest.raises(MusicError):
            ctx.authorize(other,estimate)
    with pytest.raises(MusicError):
        replace(ctx,config=None).authorize(cap,0)
    with pytest.raises(MusicError):
        replace(ctx,allow_real=False).authorize(cap,0)
    with pytest.raises(MusicError):
        replace(ctx,production=True).authorize(cap,0)
    for url in ("https://example.invalid/release_task","http://127.0.0.1:8766/release_task",
                cfg.ace_url+"/unapproved",cfg.ace_url+"/release_task?url=bad"):
        with pytest.raises(MusicError):
            local_ace.transport(cfg,ctx)(url,{},None,1,100)


def test_capabilities_are_configured_not_quality_evidence():
    cfg=local_config()
    cap=local_ace.capabilities(cfg)
    assert cap["simulated"] is False and cap["experimental"] is True
    assert cap["quality_status"]=="unverified" and cap["language_evaluated"] is None
    assert cap["origin_status"]=="operator_configured_unverified"
    assert cap["availability_status"]=="configured_not_probed"
    assert cap["supported_modes"]==["instrumental"] and not cap["vocals"] and not cap["lyrics"]
    spec=MusicSpec(prompt="Original instrumental",mode="instrumental",genres=[],moods=[],instruments=[],
                   duration_seconds=15)
    local_ace.validate_request(spec)
    for change in ({"mode":"vocals"},{"language":"Telugu"},{"duration_seconds":61}):
        with pytest.raises(MusicError):
            local_ace.validate_request(spec.model_copy(update=change))
