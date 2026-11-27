"""HTTP-to-engine boundary. The only synthesizer is engines.music.providers."""
from dataclasses import asdict
from pathlib import Path
import hashlib
import math
import wave
from engines.music.core import MusicSpec as EngineSpec, MusicOutput, GenerationContext, MusicError
from engines.music.providers import FixtureProvider
from engines.music.audio import MAX_AUDIO_BYTES
from .models import MusicSpec

def to_engine_spec(spec: MusicSpec) -> EngineSpec:
    result = EngineSpec(**spec.model_dump())
    FixtureProvider.capabilities.validate(result)
    return result

def fixture_capabilities():
    return {"available": True, **asdict(FixtureProvider.capabilities),
            "vocals": False, "lyrics": False, "exact_bpm": False,
            "genres": False, "moods": False, "instruments": False}

def validate_fixture(output: MusicOutput, directory: Path, expected_duration: int):
    cap = FixtureProvider.capabilities
    if (not output.simulated or output.provider != cap.provider or output.model != cap.model
            or output.revision != cap.revision or output.mime_type != "audio/wav"
            or output.estimated_cost_usd != 0):
        raise MusicError("unexpected fixture output identity")
    path = Path(output.artifact)
    if path.is_symlink() or path.resolve().parent != directory.resolve() or not path.is_file():
        raise MusicError("unexpected artifact path")
    if not 44 <= path.stat().st_size <= MAX_AUDIO_BYTES:
        raise MusicError("invalid artifact size")
    data = path.read_bytes()
    if len(data) != path.stat().st_size or len(data) > MAX_AUDIO_BYTES:
        raise MusicError("artifact changed")
    digest = hashlib.sha256(data).hexdigest()
    if output.metrics.get("sha256") != digest or output.metrics.get("bytes") != len(data):
        raise MusicError("artifact integrity mismatch")
    try:
        with wave.open(str(path), "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
            if len(wav.readframes(wav.getnframes())) != wav.getnframes()*wav.getnchannels()*wav.getsampwidth():
                raise MusicError("truncated WAV")
    except (wave.Error, EOFError, ZeroDivisionError) as exc:
        raise MusicError("invalid WAV") from exc
    if (not math.isfinite(output.actual_duration_seconds) or abs(duration-expected_duration)>0.01
            or abs(duration-output.actual_duration_seconds)>0.01):
        raise MusicError("fixture duration mismatch")
    # Allowlisted metadata only; never persist arbitrary provider bodies or credentials.
    provenance = {"provider":output.provider,"model":output.model,"model_revision":output.revision,
                  "simulated":True,"cost_units":0,"estimated_cost_usd":0,
                  "sha256":digest,"bytes":len(data),"seed":42,
                  "rights":"original procedural fixture"}
    return data, duration, provenance
