import io
import wave
import pytest
from pydantic import ValidationError
from synora.models import MusicSpec
from synora.provider import FixtureProvider

BASE=dict(prompt="Original melody",mode="instrumental",genres=[],moods=[],instruments=[],duration_seconds=15)

@pytest.mark.parametrize("change",[
    {"prompt":" "},{"duration_seconds":14},{"duration_seconds":121},{"duration_seconds":15.0},
    {"bpm":39},{"bpm":201},{"genres":[""]},{"genres":["x"]*13},
    {"lyrics":"not instrumental"},{"user_id":"forged"},{"mode":"unknown"}
])
def test_invalid(change):
    with pytest.raises(ValidationError):
        MusicSpec.model_validate(BASE|change)

def test_deterministic_audio():
    spec=MusicSpec.model_validate(BASE)
    values=[]
    first=FixtureProvider().generate(spec,values.append)
    second=FixtureProvider().generate(spec,lambda _:None)
    assert first.data==second.data
    assert first.provenance["simulated"] is True
    assert values==sorted(values)
    with wave.open(io.BytesIO(first.data)) as wav:
        assert wav.getnframes()/wav.getframerate()==15

def test_prompt_changes_waveform():
    a=FixtureProvider().generate(MusicSpec.model_validate(BASE),lambda _:None)
    b=FixtureProvider().generate(MusicSpec.model_validate(BASE|{"prompt":"Different prompt"}),lambda _:None)
    assert a.data!=b.data
