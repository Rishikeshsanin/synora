"""Offline preflight and independent artifact-integrity checks for ACE research."""
import argparse
import importlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import shutil

from engines.music.audio import inspect_audio
from engines.music.providers import ACE_CODE, ACE_REVISION


def preflight():
    """Probe installed tools/hardware; never download, allocate cloud GPU or infer."""
    report = {"python": platform.python_version(), "ffmpeg": bool(shutil.which("ffmpeg")),
              "ffprobe": bool(shutil.which("ffprobe")), "git": bool(shutil.which("git")),
              "ace_installed": importlib.util.find_spec("acestep") is not None,
              "torch": None, "cuda_build": None, "cuda_devices": 0, "cuda_available": False,
              "generation_executed": False, "blockers": []}
    if importlib.util.find_spec("torch") is not None:
        torch = importlib.import_module("torch")
        report.update(torch=str(torch.__version__), cuda_build=torch.version.cuda,
                      cuda_available=torch.cuda.is_available(), cuda_devices=torch.cuda.device_count())
    if not report["cuda_available"] or not report["cuda_devices"]:
        report["blockers"].append("No usable CUDA GPU; do not download weights or start inference")
    if not report["ace_installed"]:
        report["blockers"].append("Pinned ACE-Step environment not installed")
    if platform.python_version_tuple()[:2] != ("3", "12"):
        report["blockers"].append("Python 3.12 required in the pinned inference environment")
    if not all(report[key] for key in ("ffmpeg", "ffprobe", "git")):
        report["blockers"].append("Missing FFmpeg, ffprobe or Git")
    if os.getenv("SYNORA_ENV") == "production":
        report["blockers"].append("Research inference forbidden in production")
    report["ready_for_local_checks"] = not report["blockers"]
    return report


def verify(experiment_dir):
    """Validate local evidence consistency, not prove its origin or musical quality."""
    root = Path(experiment_dir).resolve(strict=True)
    manifest = root / "experiment.json"
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > 1024 * 1024:
        raise ValueError("invalid experiment manifest")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if (data.get("status") != "succeeded" or data.get("simulated") is not False
            or data.get("model") != "acestep-v15-turbo"
            or data.get("configured_snapshot_revision") != ACE_REVISION
            or data.get("upstream_code_revision") != ACE_CODE):
        raise ValueError("not a completed pinned ACE experiment")
    hashes = data.get("weight_hashes")
    if not isinstance(hashes, dict) or not hashes or any(
        not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
        for value in hashes.values()
    ):
        raise ValueError("missing or malformed checkpoint digests")
    for key in ("initialization_seconds", "generation_seconds", "gpu_total_bytes",
                "generation_peak_allocated_bytes", "generation_peak_reserved_bytes"):
        value = data.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError("missing or invalid telemetry: " + key)
    if (data["generation_peak_allocated_bytes"] > data["generation_peak_reserved_bytes"]
            or data["generation_peak_reserved_bytes"] > data["gpu_total_bytes"]):
        raise ValueError("inconsistent GPU memory telemetry")
    relative = data.get("artifact")
    if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("unsafe artifact path")
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root / "audio"):
        raise ValueError("artifact must be inside experiment audio directory")
    actual = inspect_audio(path)
    recorded = data.get("metrics")
    if not isinstance(recorded, dict) or actual["mime_type"] != "audio/wav":
        raise ValueError("invalid audio metrics")
    for key in ("sha256", "bytes", "sample_rate", "channels", "mime_type"):
        if actual[key] != recorded.get(key):
            raise ValueError("artifact mismatch: " + key)
    if data.get("duration_requested_seconds") != 15:
        raise ValueError("unexpected experiment duration target")
    recorded_duration = recorded.get("duration_seconds")
    if (type(recorded_duration) not in (int, float) or not math.isfinite(recorded_duration)
            or abs(actual["duration_seconds"] - recorded_duration) > 0.01):
        raise ValueError("recorded duration mismatch")
    return {"artifact_integrity": "passed", "inference_origin_verified": False,
            "quality_verified": False, "metrics": actual,
            "duration_error_seconds": abs(actual["duration_seconds"] - 15)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    report = verify(args.verify) if args.verify else preflight()
    print(json.dumps(report, indent=2))
    return 0 if args.verify or report["ready_for_local_checks"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
