"""Explicit, fail-closed providers. No automatic fallback or remote retries."""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import URLError
import wave
from .core import Capabilities, MusicOutput, MusicError
from .audio import inspect_audio, MAX_AUDIO_BYTES

ACE_REVISION = "eb84216a8ece2d56388e401efc28061a0c30a209"
ACE_CODE = "ca1e85fe9430179831e6bc6be790c332190a3866"
ACE_LANGUAGES = frozenset("ar az bg bn ca cs da de el en es fa fi fr he hi hr ht hu id is it ja ko la lt ms ne nl no pa pl pt ro ru sa sk sr sv sw ta te th tl tr uk ur vi yue zh unknown".split())
LYRIA_REVISION = "2026-05-20"  # API revision, not an immutable weights revision.

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def http(url, headers, payload, timeout, limit):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(url, data=data, headers={"Content-Type":"application/json", **headers})
    try:
        with build_opener(NoRedirect()).open(req, timeout=timeout) as response:
            deadline = time.monotonic() + timeout
            chunks, size = [], 0
            while True:
                if time.monotonic() >= deadline:
                    raise MusicError("provider response deadline exceeded")
                chunk = response.read1(min(65536, limit + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > limit:
                    raise MusicError("provider response too large")
            return b"".join(chunks)
    except (OSError, URLError):
        raise MusicError("provider transport failed; reconcile before retry") from None

def decode_json(raw):
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError):
        raise MusicError("invalid provider JSON") from None

def result(path, cap, ctx, cost, provenance, expected_mime=None):
    try:
        metrics = inspect_audio(path, min(60, ctx.remaining()))
        if expected_mime and metrics["mime_type"] != expected_mime:
            raise MusicError("provider returned unexpected audio format")
        ctx.remaining()
        ctx.progress(100)
        return MusicOutput(path, cap.provider, cap.model, cap.revision, metrics["duration_seconds"],
                           metrics["mime_type"], cap.simulated, provenance, cost, metrics)
    except Exception:
        path.unlink(missing_ok=True)
        raise

def save(ctx, name, audio):
    if not 12 <= len(audio) <= MAX_AUDIO_BYTES:
        raise MusicError("audio response size invalid")
    path = ctx.output_dir / name
    with path.open("xb") as f:
        f.write(audio)
    return path

def fixture_capabilities():
    """Stable JSON-compatible capability payload for the backend adapter."""
    return {"simulated": True, "vocals": False, "lyrics": False, "exact_bpm": False,
            "genres": False, "moods": False, "instruments": False, "language": False,
            "provider": "fixture", "model": "procedural-tone", "revision": "1",
            "duration_control": "exact", "min_duration_seconds": 15, "max_duration_seconds": 120,
            "limitations": ["Synthetic test tone only; no AI music or vocals"]}

class FixtureProvider:
    capabilities = Capabilities("fixture", "procedural-tone", "1", True, "exact", "synthetic",
        "simulated", "simulated", ("TEST ONLY: no vocals or AI music; ignores artistic controls",))

    def generate(self, spec, context):
        cap = self.capabilities
        cap.validate(spec)
        context.authorize(cap, 0)
        context.progress(0)
        # Original deterministic oscillator, no external recordings or lyrics.
        digest = hashlib.sha256((repr(spec) + str(context.seed)).encode()).digest()
        freq = 180 + digest[0]
        rate = 16000
        path = context.output_dir / "fixture.wav"
        with path.open("xb") as stream:
            try:
                with wave.open(stream, "wb") as w:
                    w.setparams((1, 2, rate, 0, "NONE", "not compressed"))
                    for second in range(spec.duration_seconds):
                        context.remaining()
                        samples = bytearray()
                        for i in range(rate):
                            t = second + i / rate
                            beat = 0.65 + 0.35 * math.cos(2*math.pi*(spec.bpm or 100)*t/60)
                            v = int(4500 * beat * (math.sin(2*math.pi*freq*t) + 0.3*math.sin(2*math.pi*freq*1.5*t)))
                            samples.extend(struct.pack("<h", v))
                        w.writeframesraw(samples)
                        context.progress(min(95, int(95*(second+1)/spec.duration_seconds)))
            except Exception:
                path.unlink(missing_ok=True)
                raise
        return result(path, cap, context, 0, {"seed":context.seed, "rights":"original procedural fixture", "simulated":True}, expected_mime="audio/wav")

class AceStepProvider:
    capabilities = Capabilities("ace-step", "acestep-v15-turbo", ACE_REVISION, False, "target", "target",
        "conditioned", "conditioned", ("No exact musical adherence guarantee", "Telugu pronunciation unverified",
        "Model revision must be attested by deployment; API does not prove weights", "Local cancellation does not cancel remote job"))
    def __init__(self, base_url, api_key, max_cost_usd, transport=http):
        p = urlsplit(base_url)
        if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password or p.query or p.fragment or p.path not in ("", "/"):
            raise ValueError("ACE endpoint must be a trusted operator-configured origin")
        if p.scheme == "http" and p.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("remote ACE endpoint must use HTTPS")
        if not api_key:
            raise ValueError("ACE API key required")
        self.base = base_url.rstrip("/")
        self.headers = {"Authorization":"Bearer " + api_key}
        self.cost = max_cost_usd
        self.transport = transport

    def request(self, ctx, endpoint, payload=None, raw=False):
        data = self.transport(self.base + endpoint, self.headers, payload, min(30,ctx.remaining()), MAX_AUDIO_BYTES if raw else 1024*1024)
        if raw:
            return data
        body = decode_json(data)
        if not isinstance(body,dict) or body.get("code") != 200 or body.get("error"):
            raise MusicError("ACE request failed; reconcile before retry")
        return body.get("data")

    def generate(self, spec, context):
        cap = self.capabilities
        cap.validate(spec)
        lang = {"english":"en","hindi":"hi","telugu":"te"}.get((spec.language or "").lower(), (spec.language or "unknown").lower())
        if spec.mode == "vocals" and lang not in ACE_LANGUAGES:
            raise MusicError("ACE vocal language unsupported")
        if spec.mode == "instrumental":
            lang = "unknown"
        context.authorize(cap, self.cost)
        context.progress(1)
        payload = dict(model=cap.model, prompt=spec.caption(), lyrics="[Instrumental]" if spec.mode=="instrumental" else spec.lyrics or "",
                       audio_duration=spec.duration_seconds, vocal_language=lang, audio_format="wav", batch_size=1,
                       thinking=False, use_format=False, sample_mode=False, use_random_seed=False, seed=context.seed, inference_steps=8)
        if spec.bpm:
            payload["bpm"] = spec.bpm
        # Prompt-only vocals use description mode to request lyrics from the LM.
        if spec.mode=="vocals" and not spec.lyrics:
            payload.update(sample_mode=True, sample_query=spec.caption(), thinking=True)
        task = self.request(context, "/release_task", payload)
        if not isinstance(task,dict) or not isinstance(task.get("task_id"),str) or not task["task_id"]:
            raise MusicError("ACE did not return task ID; reconcile before retry")
        task_id = task["task_id"]
        context.upstream_job(task_id)
        context.progress(10)
        while True:
            rows = self.request(context, "/query_result", {"task_id_list":[task_id]})
            if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict) or rows[0].get("task_id")!=task_id:
                raise MusicError("unexpected ACE task response")
            row = rows[0]
            if row.get("status")==2:
                raise MusicError("ACE generation failed")
            if row.get("status")==1:
                tracks = decode_json(row["result"]) if isinstance(row.get("result"),str) else row.get("result")
                if not isinstance(tracks,list) or len(tracks)!=1 or not isinstance(tracks[0],dict):
                    raise MusicError("unexpected ACE audio result")
                track = tracks[0]
                if track.get("dit_model") != cap.model:
                    raise MusicError("ACE returned unexpected model")
                url = urlsplit(track.get("file",""))
                if url.scheme or url.netloc or url.path!="/v1/audio" or not url.query.startswith("path=") or url.fragment:
                    raise MusicError("unsafe ACE audio URL")
                context.progress(85)
                audio = self.request(context, url.path+"?"+url.query, raw=True)
                path = save(context,"ace.wav",audio)
                return result(path,cap,context,self.cost,{"upstream_job_id":task_id,"seed":context.seed,
                    "configured_weights_revision":ACE_REVISION,"configured_code_revision":ACE_CODE,
                    "revision_verified_by_api":False,"lm_model":track.get("lm_model"),"cost_is_reservation_estimate":True}, expected_mime="audio/wav")
            if row.get("status")!=0:
                raise MusicError("unknown ACE task status")
            time.sleep(min(2, context.remaining()))

class LyriaProvider:
    def __init__(self, key, model="lyria-3.5", transport=http):
        if not key or model not in ("lyria-3.5","lyria-3-clip-preview"):
            raise ValueError("invalid Lyria configuration")
        fixed = 30 if model=="lyria-3-clip-preview" else None
        self.capabilities = Capabilities("lyria",model,LYRIA_REVISION,False,"fixed" if fixed else "prompt",
            "prompt","prompt","prompt",("No seed determinism", "Exact BPM, language and lyrics not guaranteed",
            "SynthID watermark; editing not supported", "API revision is not a weights hash"),fixed)
        self.key,self.transport,self.cost = key,transport,0.04 if fixed else 0.08

    def generate(self, spec, context):
        cap=self.capabilities
        cap.validate(spec)
        context.authorize(cap,self.cost)
        context.progress(1)
        prompt=spec.caption()
        if spec.lyrics:
            prompt += "\nUse these original lyrics:\n" + spec.lyrics
        data=self.transport("https://generativelanguage.googleapis.com/v1beta/interactions",
            {"x-goog-api-key":self.key,"Api-Revision":LYRIA_REVISION},
            {"model":cap.model,"input":prompt},context.remaining(),MAX_AUDIO_BYTES*2)
        body=decode_json(data)
        if not isinstance(body,dict) or body.get("error") or body.get("status") in ("failed","cancelled","requires_action"):
            raise MusicError("Lyria generation failed")
        if isinstance(body.get("id"),str):
            context.upstream_job(body["id"])
        steps = body.get("steps")
        if not isinstance(steps, list) or any(not isinstance(s, dict) for s in steps):
            raise MusicError("invalid Lyria steps")
        blocks = []
        for step in steps:
            if step.get("type") != "model_output":
                continue
            content = step.get("content")
            if not isinstance(content, list) or any(not isinstance(b, dict) for b in content):
                raise MusicError("invalid Lyria content")
            blocks.extend(b for b in content if b.get("type") == "audio")
        if len(blocks)!=1:
            raise MusicError("Lyria response lacks a single audio artifact")
        try:
            audio=base64.b64decode(blocks[0]["data"],validate=True)
        except (ValueError,KeyError,TypeError):
            raise MusicError("invalid Lyria audio encoding") from None
        context.progress(85)
        path=save(context,"lyria.mp3",audio)
        return result(path,cap,context,self.cost,{"api_revision":LYRIA_REVISION,"seed_supported":False,
            "upstream_job_id":body.get("id"),"estimated_list_price":True}, expected_mime="audio/mpeg")

def registry(env=None):
    """Availability reflects config, not a health probe or legal approval."""
    env=os.environ if env is None else env
    out={}
    if env.get("SYNORA_ENV")=="production":
        return out
    out["fixture"]=FixtureProvider()
    if env.get("SYNORA_REAL_MUSIC_APPROVED")!="1":
        return out
    if env.get("SYNORA_ACE_APPROVED")=="1":
        if env.get("SYNORA_ACE_WEIGHTS_REVISION")!=ACE_REVISION or env.get("SYNORA_ACE_CODE_REVISION")!=ACE_CODE:
            raise MusicError("ACE deployment revision attestation required")
        out["ace-step"]=AceStepProvider(env["SYNORA_ACE_URL"],env["SYNORA_ACE_KEY"],float(env["SYNORA_ACE_MAX_COST_USD"]))
    if env.get("SYNORA_LYRIA_APPROVED")=="1":
        out["lyria"]=LyriaProvider(env["GEMINI_API_KEY"],env.get("SYNORA_LYRIA_MODEL","lyria-3.5"))
    return out
