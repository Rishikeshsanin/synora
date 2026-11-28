"""Explicit local-only ACE candidate, no public/cloud provider path."""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import math
import time
import wave
from urllib.parse import urlsplit

import httpx
from engines.music.core import GenerationContext, MusicError, MusicOutput
from engines.music.providers import AceStepProvider
from engines.music.audio import MAX_AUDIO_BYTES, inspect_audio
from .config import Settings, local_origin
from .models import MusicSpec

def options(config: Settings) -> dict:
    if config.provider != "ace-step" or config.environment != "local":
        raise MusicError("local ACE not authorized")
    return {"precision_configured":config.ace_precision,
            "cpu_offload_configured":config.ace_cpu_offload,
            "weights_revision":config.ace_weights_revision,
            "code_revision":config.ace_code_revision,
            "semantic_lm":False, "experimental":True,
            "quality_status":"unverified", "language_evaluated":None}

def validate_request(spec: MusicSpec) -> None:
    if spec.mode != "instrumental" or spec.lyrics is not None or spec.language is not None:
        raise MusicError("vocals and language conditioning are not verified")
    if not 15 <= spec.duration_seconds <= 60:
        raise MusicError("local ACE duration must be 15–60 seconds")

def capabilities(config: Settings) -> dict:
    return {"available":True, "provider":"ace-step", "model":AceStepProvider.capabilities.model,
            "revision":config.ace_weights_revision, "simulated":False,
            "duration_control":"target", "min_duration_seconds":15, "max_duration_seconds":60,
            "supported_modes":["instrumental"], "vocals":False, "lyrics":False, "language":False,
            "exact_bpm":False, "genres":True, "moods":True, "instruments":True,
            "limitations":["Experimental local generation; musical adherence unverified",
                           "Vocals, lyrics and languages are disabled pending evaluation",
                           "Precision and revisions are operator-configured, not independently attested by API"],
            **options(config)}

@dataclass
class LocalAceContext(GenerationContext):
    config: Settings | None = None

    def authorize(self, capability, estimate):
        # Narrow local-free policy; the shared paid-provider gate remains unchanged.
        self.remaining()
        if (self.config is None or self.config.provider != "ace-step"
                or self.config.environment != "local" or not self.config.real_approved
                or not self.config.ace_local_approved or not self.config.ace_license_reviewed
                or not local_origin(self.config.ace_url)
                or capability != AceStepProvider.capabilities or capability.simulated
                or self.production or not self.allow_real or estimate != 0 or self.budget_usd != 0):
            raise MusicError("local free ACE authorization denied")
        self.output_dir.mkdir(parents=True, exist_ok=True)

def transport(config: Settings, context: GenerationContext):
    origin = config.ace_url
    if not local_origin(origin):
        raise MusicError("local ACE origin required")

    def request(url, headers, payload, timeout, limit):
        p = urlsplit(url)
        if (f"{p.scheme}://{p.netloc}" != origin or p.fragment
                or p.path not in ("/release_task", "/query_result", "/v1/audio")
                or (p.path != "/v1/audio" and p.query)):
            raise MusicError("local ACE transport rejected endpoint")
        deadline = time.monotonic() + min(timeout, context.remaining())
        chunks = bytearray()
        try:
            with httpx.Client(trust_env=False, follow_redirects=False, timeout=min(timeout, 30)) as client:
                method = "GET" if payload is None else "POST"
                with client.stream(method, url, headers={**headers,"Accept-Encoding":"identity"}, json=payload) as response:
                    response.raise_for_status()
                    for chunk in response.iter_raw(chunk_size=65536):
                        context.remaining()
                        if time.monotonic() >= deadline or len(chunks)+len(chunk)>limit:
                            raise MusicError("local ACE response exceeded bounds")
                        chunks.extend(chunk)
        except (httpx.HTTPError, ValueError):
            raise MusicError("local ACE transport failed; reconcile before retry") from None
        return bytes(chunks)
    return request

def provider(config: Settings, context: GenerationContext):
    options(config)
    return AceStepProvider(config.ace_url,config.ace_key,0,transport=transport(config,context))

def validate_output(output: MusicOutput, directory: Path, spec: MusicSpec, config: Settings):
    cap=AceStepProvider.capabilities
    if (output.simulated or output.provider!=cap.provider or output.model!=cap.model
            or output.revision!=config.ace_weights_revision or output.mime_type!="audio/wav"
            or output.estimated_cost_usd!=0):
        raise MusicError("unexpected local ACE identity")
    path=Path(output.artifact)
    if path.is_symlink() or path.resolve().parent!=directory.resolve() or not path.is_file():
        raise MusicError("unexpected local ACE artifact path")
    if not 44<=path.stat().st_size<=MAX_AUDIO_BYTES:
        raise MusicError("invalid local ACE artifact size")
    metrics=inspect_audio(path,60)
    data=path.read_bytes()
    digest=hashlib.sha256(data).hexdigest()
    if (len(data)>MAX_AUDIO_BYTES or metrics["sha256"]!=digest or metrics["bytes"]!=len(data)
            or output.metrics.get("sha256")!=digest or output.metrics.get("bytes")!=len(data)):
        raise MusicError("local ACE artifact integrity mismatch")
    try:
        with wave.open(str(path),"rb") as wav:
            frames=wav.getnframes()
            duration=frames/wav.getframerate()
            if (wav.getsampwidth()!=2 or wav.getnchannels() not in (1,2)
                    or not 8000<=wav.getframerate()<=192000
                    or len(wav.readframes(frames))!=frames*wav.getnchannels()*2):
                raise MusicError("local ACE requires complete PCM16 WAV")
    except (wave.Error, EOFError, ZeroDivisionError):
        raise MusicError("invalid local ACE WAV") from None
    if (not math.isfinite(output.actual_duration_seconds)
            or abs(duration-output.actual_duration_seconds)>0.05
            or abs(duration-spec.duration_seconds)>1.0):
        raise MusicError("local ACE duration mismatch")
    provenance={**options(config),"provider":cap.provider,"model":cap.model,
                "model_revision":config.ace_weights_revision,"simulated":False,
                "storage_backend":"local-ace","cost_units":0,"estimated_cost_usd":0,
                "revision_verified_by_api":False,"precision_verified_by_api":False,
                "technical_status":"validated","requested_mode":spec.mode,
                "requested_language":spec.language,"requested_duration_seconds":spec.duration_seconds,
                "actual_duration_seconds":duration,"sha256":digest,"bytes":len(data),
                "peak_dbfs":metrics["peak_dbfs"],"mean_dbfs":metrics["mean_dbfs"],
                "sample_rate":metrics["sample_rate"],"channels":metrics["channels"],
                "rights":"experimental operator-reviewed model; no commercial clearance asserted"}
    return data,duration,provenance
