"""One bounded, private ACE-Step research attempt. No services or automatic retries."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from benchmarks.music.wave6_quality import (CAPTION, CASES, QualityError, choose_precision,
                                            classify_generation_error, write_checked_pcm)

CODE = "ca1e85fe9430179831e6bc6be790c332190a3866"
REVISION = "eb84216a8ece2d56388e401efc28061a0c30a209"
MODEL = "acestep-v15-turbo"
LM_MODEL = "acestep-5Hz-lm-1.7B"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_stage(snapshot, stage, source):
    """Reuse one private staged copy; verify data bytes and allow pinned code sync."""
    weights = {}
    # Upstream may sync model-side .py from its pinned source. Allow only exact
    # snapshot or pinned tracked source Python bytes, never arbitrary staged code.
    tracked = subprocess.check_output(["git", "-C", str(source), "ls-files", "-z", "acestep/models"],
                                      text=True).split("\0")
    approved_code = {digest(source / name) for name in tracked if name.endswith(".py")}
    files = {p.relative_to(snapshot): p for p in snapshot.rglob("*") if p.is_file()}
    for relative, original in files.items():
        candidate = stage / relative
        if candidate.is_symlink() or not candidate.is_file() or not candidate.resolve().is_relative_to(stage):
            raise QualityError("staged checkpoint missing or unsafe")
        original_hash, candidate_hash = digest(original), digest(candidate)
        if original_hash != candidate_hash and not (relative.suffix == ".py" and candidate_hash in approved_code):
            raise QualityError("staged checkpoint content mismatch")
        if relative.suffix in (".safetensors", ".bin"):
            weights[str(relative)] = candidate_hash
    for candidate in stage.rglob("*"):
        if candidate.is_symlink():
            raise QualityError("symlink in staged checkpoints")
        if candidate.is_file() and candidate.relative_to(stage) not in files:
            if candidate.suffix != ".py" or digest(candidate) not in approved_code:
                raise QualityError("unexpected file in staged checkpoints")
    if not weights:
        raise QualityError("no pinned checkpoint weights")
    return weights


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ace-source", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare-checkpoints", action="store_true")
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument("--precision", choices=("auto", "fp16", "fp32", "bf16"), default="auto")
    parser.add_argument("--seed", type=int, choices=(42, 123), default=123)
    parser.add_argument("--lm", choices=("off", "semantic-pt"), default="off")
    parser.add_argument("--authorized-offline-no-charge", action="store_true")
    args = parser.parse_args()
    if not args.authorized_offline_no_charge or os.getenv("SYNORA_ENV") == "production":
        parser.error("authorized offline zero-new-spend research only; not production")
    import torch

    if not torch.cuda.is_available() or torch.version.hip is not None:
        parser.error("NVIDIA CUDA unavailable; no fallback or downloads")
    if sys.version_info[:2] != (3, 12):
        parser.error("use pinned Python 3.12 environment")
    duration, mode, language, lyrics = CASES[args.case]
    free_bytes, total_bytes = torch.cuda.mem_get_info(0)
    precision = choose_precision(mode, args.precision, torch.cuda.get_device_capability(0), free_bytes)
    dtype = {"fp16": torch.float16, "fp32": torch.float32, "bf16": torch.bfloat16}[precision]
    source, snapshot, stage, output = (p.resolve() for p in (
        args.ace_source, args.snapshot, args.checkpoint_dir, args.output))
    if (snapshot.name != REVISION or snapshot.parent.name != "snapshots" or not snapshot.is_dir()
            or not snapshot.parent.parent.name == "models--ACE-Step--Ace-Step1.5"):
        parser.error("expected pinned official HF snapshot cache path")
    if (stage.is_relative_to(snapshot.parent.parent) or stage.is_relative_to(source)
            or output.is_relative_to(stage) or output.is_relative_to(snapshot.parent.parent)
            or output.is_relative_to(source) or stage.is_relative_to(output) or output.exists()):
        parser.error("separate private checkpoint and new output directories required")
    if subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip() != CODE:
        parser.error("incorrect upstream code revision")
    if subprocess.check_output(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        parser.error("upstream tracked source must be clean")
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
                      ACESTEP_PROJECT_ROOT=str(source), ACESTEP_CHECKPOINTS_DIR=str(stage),
                      PYTHONDONTWRITEBYTECODE="1")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(source))
    import acestep
    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationConfig, GenerationParams, generate_music
    from acestep.llm_inference import LLMHandler
    from acestep.model_downloader import check_main_model_exists, check_model_exists

    if not Path(acestep.__file__).resolve().is_relative_to(source):
        parser.error("unexpected imported ACE source")
    # The pinned CUDA initializer assigns dtype itself, and _get_vae_dtype has a
    # separate CUDA policy. Override these before any model loads, not afterwards.
    class PrecisionHandler(AceStepHandler):
        @property
        def dtype(self):
            return dtype

        @dtype.setter
        def dtype(self, ignored):
            pass

        def _get_vae_dtype(self, device=None):
            return torch.float32 if (device or self.device) == "cpu" else dtype

    # A single process may use the private stage at a time. No repeat copying.
    lock = stage.with_name(stage.name + ".wave6.lock")
    with lock.open("x"):
        pass
    try:
        if stage.exists() and not stage.is_dir():
            parser.error("checkpoint stage is not a directory")
        if not stage.exists():
            if not args.prepare_checkpoints:
                parser.error("prepare private checkpoints once with --prepare-checkpoints")
            size = sum(p.stat().st_size for p in snapshot.rglob("*") if p.is_file())
            if shutil.disk_usage(stage.parent).free < size + 2 * 1024**3:
                parser.error("insufficient disk for one private checkpoint copy")
            stage.mkdir(mode=0o700)
            shutil.copytree(snapshot, stage, symlinks=False, dirs_exist_ok=True)
        weights = verify_stage(snapshot, stage, source)
        if not check_main_model_exists(stage) or not check_model_exists(MODEL, stage):
            parser.error("required pinned checkpoints missing")
        if args.lm != "off" and not check_model_exists(LM_MODEL, stage):
            parser.error("pinned LM checkpoint missing")
        output.mkdir(mode=0o700)
        caption = "Original calm cinematic instrumental, soft piano and warm strings" if mode == "instrumental" else CAPTION
        metadata = {"status": "started", "case": args.case, "simulated": False,
                    "code_revision": CODE, "snapshot_revision": REVISION, "weight_sha256": weights,
                    "requested_precision": args.precision, "effective_precision": precision,
                    "gpu": torch.cuda.get_device_name(0), "gpu_free_before_bytes": free_bytes,
                    "gpu_total_bytes": total_bytes, "torch": str(torch.__version__), "cuda": torch.version.cuda,
                    "seed": args.seed, "duration_requested_seconds": duration, "language": language,
                    "mode": mode, "caption": caption, "lyrics": lyrics, "bpm": 90,
                    "inference_steps": 8, "offload_to_cpu": True, "offload_dit_to_cpu": precision == "fp32",
                    "lm": args.lm, "lm_dtype": "fp32" if args.lm != "off" else None,
                    "technical_status": "pending", "semantic_status": "pending_review", "actual_cost_usd": None,
                    "additional_normalization": False, "upstream_peak_guard": True}
        report = output / "experiment.json"
        report.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
        try:
            torch.cuda.reset_peak_memory_stats()
            start = time.perf_counter()
            handler = PrecisionHandler()
            _, ok = handler.initialize_service(project_root=str(source), config_path=MODEL, device="cuda",
                use_flash_attention=False, compile_model=False, offload_to_cpu=True,
                offload_dit_to_cpu=precision == "fp32", vae_checkpoint="official")
            if not ok:
                raise QualityError("DiT initialization failed; inspect local logs")
            actual_dtype = next(p.dtype for p in handler.model.parameters() if p.is_floating_point())
            if handler.dtype != dtype or actual_dtype != dtype:
                raise QualityError("loaded DiT dtype differs from requested precision")
            metadata["loaded_dit_dtype"] = str(actual_dtype)
            lm = None
            if args.lm != "off":
                lm = LLMHandler()
                _, ok = lm.initialize(checkpoint_dir=str(stage), lm_model_path=LM_MODEL, backend="pt",
                                      device="cuda", offload_to_cpu=True, dtype=torch.float32)
                if not ok or not lm.llm_initialized or lm.dtype != torch.float32:
                    raise QualityError("LM initialization/precision failed")
            torch.cuda.synchronize()
            metadata["initialization_seconds"] = time.perf_counter() - start
            metadata["initialization_peak_allocated_bytes"] = torch.cuda.max_memory_allocated()
            params = GenerationParams(caption=caption, lyrics=lyrics, instrumental=mode == "instrumental",
                vocal_language=language, duration=duration, bpm=90, seed=args.seed, inference_steps=8,
                thinking=lm is not None, use_cot_caption=False, use_cot_metas=False,
                use_cot_language=False, use_cot_lyrics=False, enable_normalization=False)
            config = GenerationConfig(batch_size=1, use_random_seed=False, seeds=[args.seed], audio_format="wav")
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
            start = time.perf_counter()
            # No upstream saver: validate original float tensor before PCM conversion.
            result = generate_music(handler, lm, params, config, save_dir=None)
            torch.cuda.synchronize()
            metadata["generation_seconds"] = time.perf_counter() - start
            metadata["generation_peak_allocated_bytes"] = torch.cuda.max_memory_allocated()
            metadata["generation_peak_reserved_bytes"] = torch.cuda.max_memory_reserved()
            if not result.success or len(result.audios) != 1:
                metadata["failure_class"] = classify_generation_error(result.error)
                raise QualityError("generation failed; no retry or fallback")
            audio = result.audios[0]
            if lm is not None:
                codes = audio.get("params", {}).get("audio_codes")
                if not isinstance(codes, str) or not codes.strip():
                    raise QualityError("requested LM semantic codes absent")
                metadata["lm_codes_sha256"] = hashlib.sha256(codes.encode()).hexdigest()
                metadata["lm_codes_characters"] = len(codes)
            tensor = audio.get("tensor")
            if not isinstance(tensor, torch.Tensor) or tensor.ndim != 2 or not tensor.is_floating_point():
                raise QualityError("invalid generated audio tensor")
            channels, frames = tensor.shape
            blocks = (tensor[:, offset:offset + 8192].detach().to(device="cpu", dtype=torch.float32)
                      .transpose(0, 1).contiguous().view(-1).tolist() for offset in range(0, frames, 8192))
            metadata["metrics"] = write_checked_pcm(output / "audio.wav", blocks, audio["sample_rate"],
                                                     channels, frames, duration)
            metadata.update(status="technical_pass", technical_status="passed", artifact="audio.wav")
        except Exception as exc:
            metadata.update(status="failed", technical_status="failed", error_type=type(exc).__name__)
            # No provider response, arbitrary exception strings or tokens in evidence.
            if isinstance(exc, QualityError):
                metadata["failure_reason"] = str(exc)
            raise
        finally:
            report.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    finally:
        lock.unlink(missing_ok=True)
    print("Technical audio pass only; human semantic review required:", report)


if __name__ == "__main__":
    main()
