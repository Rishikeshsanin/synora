"""Single original instrumental experiment on an authorized, locally attached GPU.

Requires the pinned upstream ACE environment and a previously downloaded pinned
Hugging Face snapshot. No provider API, account creation, or server.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from engines.music.audio import inspect_audio
from engines.music.providers import ACE_CODE, ACE_REVISION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ace-source", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authorized-local-gpu", action="store_true",
                        help="Confirm authorized, zero-new-spend local/notebook GPU and offline execution")
    args = parser.parse_args()
    if not args.authorized_local_gpu:
        parser.error("explicit operator authorization required")
    source = args.ace_source.resolve()
    snapshot = args.snapshot.resolve()
    output = args.output.resolve()
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(source), "status", "--porcelain",
                                     "--untracked-files=no"], text=True).strip()
    if commit != ACE_CODE or dirty:
        parser.error("upstream source must be at the clean pinned commit")
    if not snapshot.is_dir() or snapshot.name != ACE_REVISION or snapshot.parent.name != "snapshots":
        parser.error("use the pinned Hugging Face cache snapshot")
    if output.exists() or output.is_relative_to(source) or output.is_relative_to(snapshot.parent.parent):
        parser.error("use a new output directory outside source and model cache")
    if not output.parent.is_dir():
        parser.error("output parent must already exist")
    # Copy instead of allowing upstream model-code synchronization to alter the HF cache.
    checkpoint = output / "checkpoints"
    size = sum(p.stat().st_size for p in snapshot.rglob("*") if p.is_file())
    if shutil.disk_usage(output.parent).free < size + 2 * 1024**3:
        parser.error("insufficient disk for isolated checkpoint copy")
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                      HF_HUB_DISABLE_TELEMETRY="1", ACESTEP_PROJECT_ROOT=str(source),
                      ACESTEP_CHECKPOINTS_DIR=str(checkpoint))
    import torch
    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationConfig, GenerationParams, generate_music
    from acestep.model_downloader import check_main_model_exists, check_model_exists

    if not torch.cuda.is_available():
        parser.error("CUDA GPU unavailable; no CPU fallback")
    if not check_main_model_exists(snapshot) or not check_model_exists("acestep-v15-turbo", snapshot):
        parser.error("pinned snapshot missing required checkpoints")
    output.mkdir(mode=0o700)
    shutil.copytree(snapshot, checkpoint, symlinks=False)
    # Record content hashes of copied weight artifacts prior to any upstream code sync.
    weight_hashes = {}
    for path in sorted(checkpoint.rglob("*")):
        if path.is_file() and path.suffix in (".safetensors", ".bin"):
            with path.open("rb") as stream:
                weight_hashes[str(path.relative_to(checkpoint))] = hashlib.file_digest(stream, "sha256").hexdigest()
    if not weight_hashes:
        raise RuntimeError("no checkpoint weight files found")
    metadata = {"model": "acestep-v15-turbo", "configured_snapshot_revision": ACE_REVISION,
                "upstream_code_revision": commit, "snapshot_path_revision_checked": True,
                "weight_hashes": weight_hashes, "torch": torch.__version__,
                "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0),
                "gpu_total_bytes": torch.cuda.get_device_properties(0).total_memory,
                "seed": 42, "duration_requested_seconds": 15, "simulated": False,
                "quality_score": None, "prompt_adherence_score": None,
                "actual_cost_usd": None, "status": "started"}
    evidence = output / "experiment.json"
    evidence.write_text(json.dumps(metadata, indent=2))
    try:
        handler = AceStepHandler()
        torch.cuda.reset_peak_memory_stats()
        start = time.perf_counter()
        _, ok = handler.initialize_service(project_root=str(source),
            config_path="acestep-v15-turbo", device="cuda", use_flash_attention=False,
            compile_model=False, offload_to_cpu=True, vae_checkpoint="official")
        if not ok:
            raise RuntimeError("ACE initialization failed; inspect local upstream logs")
        torch.cuda.synchronize()
        metadata["initialization_seconds"] = time.perf_counter() - start
        metadata["initialization_peak_allocated_bytes"] = torch.cuda.max_memory_allocated()
        params = GenerationParams(caption="Original calm cinematic instrumental, soft piano and warm strings",
            lyrics="[Instrumental]", instrumental=True, vocal_language="unknown",
            duration=15, bpm=90, inference_steps=8, seed=42, thinking=False,
            use_cot_caption=False, use_cot_metas=False, use_cot_language=False,
            enable_normalization=False)
        config = GenerationConfig(batch_size=1, use_random_seed=False, seeds=[42], audio_format="wav")
        audio_dir = output / "audio"
        audio_dir.mkdir()
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
        start = time.perf_counter()
        result = generate_music(handler, None, params, config, save_dir=str(audio_dir))
        torch.cuda.synchronize()
        metadata["generation_seconds"] = time.perf_counter() - start
        metadata["generation_peak_allocated_bytes"] = torch.cuda.max_memory_allocated()
        metadata["generation_peak_reserved_bytes"] = torch.cuda.max_memory_reserved()
        if not result.success or len(result.audios) != 1:
            raise RuntimeError("ACE generation did not return one artifact")
        artifact = Path(result.audios[0]["path"]).resolve()
        if not artifact.is_relative_to(audio_dir):
            raise RuntimeError("unexpected artifact location")
        metrics = inspect_audio(artifact)
        if metrics["mime_type"] != "audio/wav":
            raise RuntimeError("unexpected artifact MIME")
        metadata.update(status="succeeded", artifact=str(artifact.relative_to(output)),
                        metrics=metrics, duration_error_seconds=abs(metrics["duration_seconds"] - 15))
    except Exception as exc:
        metadata.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        evidence.write_text(json.dumps(metadata, indent=2))
    print("Generated one local artifact; inspect", evidence)


if __name__ == "__main__":
    main()
