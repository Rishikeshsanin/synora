import pytest
from pydantic import ValidationError
from synora.models import MusicSpec
from synora.provider import to_engine_spec, validate_fixture, fixture_capabilities
from engines.music.core import GenerationContext, MusicError
from engines.music.providers import FixtureProvider
from dataclasses import replace

BASE=dict(prompt="Original melody",mode="instrumental",genres=[],moods=[],instruments=[],duration_seconds=15)

@pytest.mark.parametrize("change",[
    {"prompt":" "},{"duration_seconds":14},{"duration_seconds":121},{"duration_seconds":15.0},
    {"bpm":39},{"bpm":201},{"genres":[""]},{"genres":["x"]*13},{"instruments":["x"]*13},
    {"lyrics":"not instrumental"},{"lyrics":""},{"mode":"vocals","lyrics":" "},
    {"language":"x"*33},{"user_id":"forged"},{"mode":"unknown"}
])
def test_invalid(change):
    with pytest.raises(ValidationError):
        MusicSpec.model_validate(BASE|change)

def generate(directory, spec, progress=lambda _:None):
    return FixtureProvider().generate(to_engine_spec(MusicSpec.model_validate(spec)),
                                      GenerationContext(directory,progress=progress))

def test_deterministic_audio(tmp_path):
    values=[]
    first=generate(tmp_path/"a",BASE,values.append)
    second=generate(tmp_path/"b",BASE)
    data,duration,provenance=validate_fixture(first,tmp_path/"a",15)
    assert data==second.artifact.read_bytes()
    assert provenance["simulated"] is True and duration==15
    assert values==sorted(values)
    assert fixture_capabilities()["vocals"] is False

def test_prompt_changes_waveform(tmp_path):
    a=generate(tmp_path/"a",BASE)
    b=generate(tmp_path/"b",BASE|{"prompt":"Different prompt"})
    assert a.artifact.read_bytes()!=b.artifact.read_bytes()

def test_artifact_validation(tmp_path):
    output=generate(tmp_path,BASE)
    for forged in (replace(output,simulated=False),replace(output,actual_duration_seconds=30),
                   replace(output,mime_type="audio/mpeg"),replace(output,estimated_cost_usd=1)):
        with pytest.raises(MusicError):
            validate_fixture(forged,tmp_path,15)
    output.artifact.write_bytes(output.artifact.read_bytes()+b"tampered")
    with pytest.raises(MusicError):
        validate_fixture(output,tmp_path,15)

def test_engine_cancel(tmp_path):
    with pytest.raises(MusicError):
        FixtureProvider().generate(to_engine_spec(MusicSpec.model_validate(BASE)),
                                   GenerationContext(tmp_path,cancelled=lambda:True))
    assert not list(tmp_path.iterdir())
