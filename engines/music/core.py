"""Worker-facing v0.1 interface. No database or billing side effects."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol
import math
import time

class MusicError(RuntimeError):
    """Safe provider error; remote response bodies must not be exposed."""

@dataclass(frozen=True)
class MusicSpec:
    prompt: str
    mode: str = "instrumental"
    genres: tuple[str, ...] = ()
    moods: tuple[str, ...] = ()
    instruments: tuple[str, ...] = ()
    duration_seconds: int = 30
    bpm: int | None = None
    lyrics: str | None = None
    language: str | None = None

    def __post_init__(self):
        if not isinstance(self.prompt, str) or not 1 <= len(self.prompt.strip()) <= 2000:
            raise ValueError("prompt must contain 1–2000 characters")
        if self.mode not in ("instrumental", "vocals"):
            raise ValueError("invalid mode")
        if type(self.duration_seconds) is not int or not 15 <= self.duration_seconds <= 120:
            raise ValueError("duration must be 15–120 seconds")
        if self.bpm is not None and (type(self.bpm) is not int or not 40 <= self.bpm <= 200):
            raise ValueError("bpm must be 40–200")
        for name in ("genres", "moods", "instruments"):
            values = getattr(self, name)
            if not isinstance(values, (list, tuple)) or len(values) > 12 or any(
                not isinstance(v, str) or not 1 <= len(v.strip()) <= 80 for v in values
            ):
                raise ValueError("invalid " + name)
            object.__setattr__(self, name, tuple(values))
        if self.lyrics is not None and (not isinstance(self.lyrics, str) or not 1 <= len(self.lyrics.strip()) <= 6000):
            raise ValueError("invalid lyrics")
        if self.language is not None and (not isinstance(self.language, str) or not 1 <= len(self.language.strip()) <= 32):
            raise ValueError("invalid language")
        if self.mode == "instrumental" and self.lyrics is not None:
            raise ValueError("instrumental mode cannot contain lyrics")

    def caption(self):
        parts = [self.prompt, "Instrumental only, no vocals" if self.mode == "instrumental" else "Sung vocals"]
        for name in ("genres", "moods", "instruments"):
            values = getattr(self, name)
            if values:
                parts.append(name + ": " + ", ".join(values))
        if self.bpm:
            parts.append(f"Target tempo: {self.bpm} BPM")
        if self.language and self.mode == "vocals":
            parts.append("Vocal language: " + self.language)
        parts.append(f"Target duration: {self.duration_seconds} seconds")
        return ". ".join(parts)

@dataclass(frozen=True)
class Capabilities:
    provider: str
    model: str
    revision: str
    simulated: bool
    duration_control: str
    bpm_control: str
    lyrics_control: str
    language_control: str
    limitations: tuple[str, ...]
    fixed_duration: int | None = None

    def validate(self, spec):
        if self.fixed_duration is not None and spec.duration_seconds != self.fixed_duration:
            raise MusicError("requested duration unsupported by this model")
        if spec.lyrics and self.lyrics_control == "unsupported":
            raise MusicError("lyrics unsupported by this model")

@dataclass
class GenerationContext:
    output_dir: Path
    seed: int = 42
    timeout_seconds: float = 300
    cancelled: Callable[[], bool] = lambda: False
    progress: Callable[[int], None] = lambda _: None
    allow_real: bool = False
    budget_usd: float = 0
    production: bool = False
    # Persist upstream job ID immediately in the backend for reconciliation.
    upstream_job: Callable[[str], None] = lambda _: None
    started: float = field(default_factory=time.monotonic, init=False)

    def __post_init__(self):
        if not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 900:
            raise ValueError("invalid timeout")
        if not math.isfinite(self.budget_usd) or self.budget_usd < 0:
            raise ValueError("invalid budget")
        if type(self.seed) is not int or not 0 <= self.seed <= 2147483647:
            raise ValueError("invalid seed")
        self.output_dir = Path(self.output_dir)

    def remaining(self):
        if self.cancelled():
            raise MusicError("cancelled locally; upstream may continue")
        left = self.timeout_seconds - (time.monotonic() - self.started)
        if left <= 0:
            raise MusicError("generation deadline exceeded; upstream may continue")
        return left

    def authorize(self, capability, estimate):
        self.remaining()
        if capability.simulated:
            if self.production:
                raise MusicError("fixture forbidden in production")
        elif not self.allow_real or estimate is None or estimate <= 0 or not math.isfinite(estimate) or estimate > self.budget_usd:
            raise MusicError("real inference requires approved bounded budget")
        self.output_dir.mkdir(parents=True, exist_ok=True)

@dataclass(frozen=True)
class MusicOutput:
    artifact: Path
    provider: str
    model: str
    revision: str
    actual_duration_seconds: float
    mime_type: str
    simulated: bool
    provenance: dict
    estimated_cost_usd: float | None
    metrics: dict

class MusicProvider(Protocol):
    capabilities: Capabilities
    def generate(self, spec: MusicSpec, context: GenerationContext) -> MusicOutput: ...
