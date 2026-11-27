"""Explicit deterministic synthetic waveform, not AI music."""
import hashlib
import io
import math
import struct
import wave
from dataclasses import dataclass
from typing import Protocol, Callable
from .models import MusicSpec

@dataclass(frozen=True)
class Artifact:
    data: bytes
    duration_seconds: int
    provenance: dict

class MusicProvider(Protocol):
    capabilities: dict
    def generate(self, spec: MusicSpec, context: Callable[[int], None]) -> Artifact: ...

class FixtureProvider:
    capabilities = {"simulated": True, "vocals": False, "lyrics": False, "exact_bpm": False,
                    "genres": False, "moods": False, "instruments": False}
    def generate(self, spec: MusicSpec, context: Callable[[int], None]) -> Artifact:
        rate=8000
        freq=220+hashlib.sha256(spec.prompt.encode()).digest()[0]
        out=io.BytesIO()
        with wave.open(out,"wb") as w:
            w.setparams((1,2,rate,0,"NONE","not compressed"))
            for second in range(spec.duration_seconds):
                frames=bytearray()
                for i in range(rate):
                    t=second+i/rate
                    envelope=min(1,t*8,(spec.duration_seconds-t)*8)
                    frames.extend(struct.pack("<h",int(3500*envelope*math.sin(2*math.pi*freq*t))))
                w.writeframesraw(frames)
                context(10+int(75*(second+1)/spec.duration_seconds))
        return Artifact(out.getvalue(),spec.duration_seconds,
                        {"provider":"fixture","model_revision":"synthetic-wave-v1","simulated":True,"cost_units":0})
