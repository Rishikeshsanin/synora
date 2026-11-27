"""CI artifact allowlist. No raw logs, JUnit text, browser state or private media."""
import hashlib
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def junit_summary(paths):
    summaries = []
    for path in paths:
        path = Path(path)
        if not path.is_file():
            summaries.append({"suite": path.stem, "status": "not_run"})
            continue
        cases = list(ET.parse(path).getroot().iter("testcase"))
        counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
        for case in cases:
            status = ("errors" if case.find("error") is not None else
                      "failed" if case.find("failure") is not None else
                      "skipped" if case.find("skipped") is not None else "passed")
            counts[status] += 1
        summaries.append({"suite": path.stem, "status": "executed" if cases else "empty",
                          "total": len(cases), **counts})
    return summaries


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def stage_media(root, destination):
    root, destination = Path(root).resolve(), Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    ratios = ("9x16", "16x9", "1x1")
    allowlist = {
        "synora-ad-demo": [r + ".mp4" for r in ratios],
        "synora-wave2-demo": [r + ".mp4" for r in ratios],
        "synora-editorial-demo": [r + "-" + style + ".mp4" for r in ratios
                                  for style in ("classic", "editorial-v1")],
    }
    results = []
    for group, names in allowlist.items():
        for name in names:
            source = root / group / name
            if (source.is_symlink() or not source.resolve().is_relative_to(root)
                    or not source.is_file() or not 0 < source.stat().st_size <= 50 * 1024 * 1024):
                raise ValueError("Missing or invalid synthetic render: " + group + "/" + name)
            probe = json.loads(subprocess.check_output([
                "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(source)
            ], timeout=20))
            video = next(s for s in probe["streams"] if s["codec_type"] == "video")
            audio = next(s for s in probe["streams"] if s["codec_type"] == "audio")
            if video["codec_name"] != "h264" or audio["codec_name"] != "aac":
                raise ValueError("Unexpected render codecs")
            target = destination / group / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            results.append({"file": group + "/" + name, "synthetic": True,
                            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                            "width": video["width"], "height": video["height"],
                            "seconds": float(probe["format"]["duration"]), "bytes": target.stat().st_size})
    write_json(destination / "manifest.json", results)
    print(f"Staged {len(results)} generated synthetic renders; no private media or raw source assets")


if __name__ == "__main__":
    mode, destination, *paths = sys.argv[1:]
    if mode == "junit":
        write_json(destination, junit_summary(paths))
    elif mode == "media" and len(paths) == 1:
        stage_media(destination, paths[0])
    else:
        raise SystemExit("Invalid evidence command")
