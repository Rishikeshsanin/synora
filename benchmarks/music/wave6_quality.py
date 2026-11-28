"""Pure-CPU experiment controls and pre-quantization audio acceptance checks."""
from array import array
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import wave


class QualityError(ValueError):
    """Rejected research output; never silently replace it with a fixture."""


CAPTION = "Original gentle acoustic pop, clear solo sung lead, soft piano, 90 BPM"
CASES = {
    "instrumental15": (15, "instrumental", "unknown", "[Instrumental]"),
    "instrumental60": (60, "instrumental", "unknown", "[Instrumental]"),
    "english": (30, "vocals", "en", "[Verse]\nMorning light upon the sea\nA new road waits for me"),
    "telugu-native": (30, "vocals", "te", "[Verse]\nవెన్నెల దారిలో నడుద్దాం\nకొత్త ఆశల పాట పాడుదాం"),
    "telugu-roman": (30, "vocals", "te", "[Verse]\nVennela daarilo naduddaam\nKotta aashala paata paadudaam"),
    "hindi-native": (30, "vocals", "hi", "[Verse]\nचाँदनी की राह चलें\nनई उम्मीद का गीत गाएँ"),
    "hindi-roman": (30, "vocals", "hi", "[Verse]\nChaandni ki raah chalein\nNayi ummeed ka geet gaayen"),
}


def choose_precision(mode, requested, capability, free_bytes):
    """Conservative research policy, not a hardware feasibility guarantee."""
    if mode not in ("instrumental", "vocals") or requested not in ("auto", "fp16", "fp32", "bf16"):
        raise QualityError("invalid precision or mode")
    if capability < (7, 0):
        raise QualityError("unsupported GPU for this experiment")
    precision = ("fp32" if mode == "vocals" else "fp16") if requested == "auto" else requested
    if precision == "bf16" and capability < (8, 0):
        raise QualityError("native BF16 requires Ampere or newer")
    minimum = 12 if precision == "fp32" else 8
    if free_bytes < minimum * 1024**3:
        raise QualityError("insufficient free VRAM for conservative experiment gate")
    return precision


def write_checked_pcm(destination, blocks, rate, channels, frames, target_seconds):
    """Validate finite floating samples BEFORE PCM16 conversion, then publish once.

    Blocks contain interleaved normalized floats. No normalization, clipping repair,
    resampling or hidden retry. The WAV is not published on a failed technical gate.
    """
    destination = Path(destination)
    if (type(rate) is not int or type(channels) is not int or type(frames) is not int
            or not 8000 <= rate <= 48000 or channels not in (1, 2)
            or not 0 < frames <= 120 * rate or target_seconds not in (15, 30, 60)):
        raise QualityError("invalid audio shape or target")
    duration = frames / rate
    if abs(duration - target_seconds) > max(0.25, target_seconds * 0.02):
        raise QualityError("duration outside experimental tolerance")
    if destination.suffix != ".wav" or destination.exists() or destination.is_symlink():
        raise QualityError("new WAV destination required")
    count = clipped = quiet = 0
    total_squares = peak = 0.0
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".wave6-", delete=False) as temp:
        staging = Path(temp.name)
    try:
        with wave.open(str(staging), "wb") as out:
            out.setparams((channels, 2, rate, frames, "NONE", "not compressed"))
            for block in blocks:
                pcm = array("h")
                for value in block:
                    count += 1
                    if count > frames * channels or not math.isfinite(value):
                        raise QualityError("nonfinite or excess audio samples")
                    magnitude = abs(value)
                    if magnitude > 1:
                        raise QualityError("out-of-range audio sample; no clipping repair")
                    peak = max(peak, magnitude)
                    total_squares += value * value
                    clipped += magnitude >= 0.999
                    quiet += magnitude < 0.001
                    pcm.append(round(value * 32767))
                if sys.byteorder != "little":
                    pcm.byteswap()
                out.writeframesraw(pcm.tobytes())
        if count != frames * channels:
            raise QualityError("incomplete audio tensor")
        rms = math.sqrt(total_squares / count)
        if peak < 0.003 or rms < 0.001:
            raise QualityError("silent or near-silent audio")
        if clipped / count > 0.01:
            raise QualityError("excess near-full-scale samples")
        with staging.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        os.link(staging, destination)  # exclusive publication; never overwrite
        return {"sha256": digest, "duration_seconds": duration, "sample_rate": rate,
                "channels": channels, "frames": frames, "peak_dbfs": 20 * math.log10(peak),
                "rms_dbfs": 20 * math.log10(rms), "near_full_scale_fraction": clipped / count,
                "near_silent_sample_fraction": quiet / count, "technical_status": "passed",
                "semantic_status": "pending_review"}
    finally:
        staging.unlink(missing_ok=True)


def semantic_status(mode, review):
    """Human rubric only. Valid PCM is never evidence of vocals or lyric fidelity."""
    if mode not in ("instrumental", "vocals"):
        raise QualityError("unknown review mode")
    fields = ("musical_coherence", "requested_style", "instrumental_only") if mode == "instrumental" else (
        "musical_coherence", "requested_style", "vocals_present", "language_match", "lyrics_match")
    values = [review.get(field) for field in fields]
    if any(value is not None and type(value) is not bool for value in values):
        raise QualityError("review must use true, false or null")
    if False in values:
        return "failed"
    return "passed" if all(value is True for value in values) else "pending_review"


def classify_generation_error(error):
    """Classify known pinned upstream failures; never persist arbitrary error text."""
    text = error if isinstance(error, str) else ""
    if "Generation produced NaN or Inf latents" in text:
        return "nonfinite_latents"
    if "Generation produced zero latents" in text:
        return "zero_latents"
    return "generation_failed"


def review_experiment(root, review):
    """Bind human listening assertions to exact technically accepted audio bytes."""
    root = Path(root).resolve(strict=True)
    manifest, artifact = root / "experiment.json", root / "audio.wav"
    if (manifest.is_symlink() or artifact.is_symlink() or not manifest.is_file()
            or not artifact.is_file() or manifest.stat().st_size > 1024 * 1024
            or artifact.stat().st_size > 80 * 1024 * 1024):
        raise QualityError("invalid private experiment files")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if (data.get("status") != "technical_pass" or data.get("technical_status") != "passed"
            or data.get("simulated") is not False or data.get("artifact") != "audio.wav"):
        raise QualityError("not a technically accepted research artifact")
    with artifact.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != data.get("metrics", {}).get("sha256"):
        raise QualityError("audio changed since technical acceptance")
    if review.get("listened_to_exact_artifact") is not True or review.get("audio_sha256") != digest:
        raise QualityError("human listening and matching audio hash required")
    status = semantic_status(data.get("mode"), review)
    fields = ("musical_coherence", "requested_style", "instrumental_only", "vocals_present",
              "language_match", "lyrics_match")
    return {"audio_sha256": digest, "case": data.get("case"), "mode": data.get("mode"),
            "human_attested": True, "inference_origin_verified": False, "semantic_status": status,
            "review": {key: review.get(key) for key in fields if key in review}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment", type=Path)
    parser.add_argument("review_input", type=Path, help="Private JSON human listening review")
    args = parser.parse_args()
    if args.review_input.stat().st_size > 16384:
        parser.error("review input too large")
    result = review_experiment(args.experiment, json.loads(args.review_input.read_text(encoding="utf-8")))
    with (args.experiment / "review.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result, indent=2))
    return 0 if result["semantic_status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
