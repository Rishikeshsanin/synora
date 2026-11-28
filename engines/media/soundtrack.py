"""Bounded, offline soundtrack intake for trusted local advertising projects."""
import hashlib
import hmac
import io
import json
import math
import os
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np
import soundfile as sf

MAX_SOURCE = 48 * 1024 * 1024
KINDS = ('synthetic-fixture', 'user-supplied', 'generated-unverified')
RIGHTS = ('source', 'derivative', 'advertising_sync')


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _read(path, limit=MAX_SOURCE):
    with Path(path).open('rb') as f:
        data = f.read(limit + 1)
    if not data or len(data) > limit:
        raise ValueError('empty or oversized WAV')
    return data


def _review(provenance, rights):
    if not isinstance(rights, dict) or any(rights.get(k) is not True for k in RIGHTS):
        raise ValueError('source, derivative and advertising sync rights required')
    if not isinstance(provenance, dict) or provenance.get('kind') not in KINDS:
        raise ValueError('explicit source provenance required')
    fields = ('kind', 'source_id', 'provider', 'revision')
    if any(k not in fields for k in provenance):
        raise ValueError('unsupported provenance field')
    required = ('source_id', 'provider', 'revision') if provenance['kind'] == 'generated-unverified' else ('source_id',)
    if any(not isinstance(provenance.get(k), str) or not provenance[k].strip() for k in required):
        raise ValueError('missing provenance detail')
    if any(not isinstance(v, str) or len(v) > 200 or not v.isprintable() for v in provenance.values()):
        raise ValueError('invalid provenance detail')


def _pcm(samples, rate):
    out = io.BytesIO()
    with wave.open(out, 'wb') as f:
        f.setnchannels(samples.shape[1])
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(np.clip(np.rint(samples * 32768), -32768, 32767).astype('<i2').tobytes())
    return out.getvalue()


def measure(wav):
    is_bytes = isinstance(wav, bytes)
    run = subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-i', 'pipe:0' if is_bytes else str(wav), '-af',
                          'loudnorm=I=-16:TP=-2:LRA=11:print_format=json', '-f', 'null', '-'],
                         input=wav if is_bytes else None, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                         check=True, timeout=30)
    log = run.stderr.decode('utf-8', errors='replace')
    report = json.loads(log[log.rfind('{'):log.rfind('}')+1])
    loudness, peak = float(report['input_i']), float(report['input_tp'])
    if not math.isfinite(loudness) or not math.isfinite(peak):
        raise ValueError('silent or unmeasurable soundtrack')
    return dict(lufs=loudness, dbtp=peak)


def prepare(path, provenance, rights, start_frame, frame_count):
    """Return a PCM16 preview and receipt; no model inference or automatic approval."""
    _review(provenance, rights)
    source = _read(path)
    if type(start_frame) is not int or type(frame_count) is not int or start_frame < 0:
        raise ValueError('integer sample-frame selection required')
    with sf.SoundFile(io.BytesIO(source)) as f:
        rate, channels, total = f.samplerate, f.channels, f.frames
        if (f.format not in ('WAV', 'WAVEX') or f.subtype not in ('PCM_16', 'PCM_24', 'PCM_32', 'FLOAT', 'DOUBLE')
                or not 8000 <= rate <= 48000 or channels not in (1, 2) or not 3*rate <= total <= 120*rate):
            raise ValueError('unsupported WAV format or duration')
        if not 3*rate <= frame_count <= 60*rate or start_frame+frame_count > total:
            raise ValueError('selection outside 3–60 second preview or source bounds')
        f.seek(start_frame)
        samples = f.read(frame_count, dtype='float64', always_2d=True)
    if len(samples) != frame_count or not np.isfinite(samples).all() or np.max(np.abs(samples)) > 1.0:
        raise ValueError('truncated, non-finite or out-of-range audio')
    # Smooth only the selected boundary; no dynamics compression or invented vocals.
    fade_in, fade_out = round(rate*.05), round(rate*.15)
    samples[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    samples[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    before = measure(_pcm(samples, rate))
    gain = min(12.0, -16.0-before['lufs'], -2.2-before['dbtp'])
    samples *= 10**(gain/20)
    output = _pcm(samples, rate)
    after = measure(output)
    if after['dbtp'] > -2.0:
        correction = -2.2-after['dbtp']
        gain += correction
        samples *= 10**(correction/20)
        output = _pcm(samples, rate)
        after = measure(output)
    if after['dbtp'] > -2.0 or after['lufs'] > -15.8:
        raise ValueError('soundtrack loudness or true-peak limit exceeded')
    receipt = dict(version='soundtrack-v1', source_sha256=_sha(source), audio_sha256=_sha(output),
                   provenance=dict(provenance), rights={k: True for k in RIGHTS}, rate=rate, channels=channels,
                   source_frames=total, start_frame=start_frame, frame_count=frame_count,
                   gain_db=round(gain, 4), before=before, after=after, inference_verified=False)
    return output, receipt


def project_key(master_key, project_id):
    if not isinstance(master_key, bytes) or len(master_key) < 32:
        raise ValueError('trusted project master key required')
    if not isinstance(project_id, str) or not project_id.strip() or len(project_id) > 128 or not project_id.isprintable():
        raise ValueError('invalid project ID')
    return hmac.new(master_key, b'synora-ad-project-v1\0'+project_id.encode(), hashlib.sha256).digest()


def _private(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir() or (os.name == 'posix' and path.stat().st_mode & 0o077):
        raise ValueError('private cache directory required')


def project_cache(root, master_key, project_id):
    key = project_key(master_key, project_id)
    root = Path(root)
    _private(root)
    child = root / hmac.new(key, b'cache-directory-v1', hashlib.sha256).hexdigest()
    _private(child)
    return child


def bind_soundtrack(board, receipt, project_id):
    """Return reviewable board; caller must separately approve with project_key."""
    _review(receipt['provenance'], receipt['rights'])
    if receipt.get('version') != 'soundtrack-v1' or receipt.get('inference_verified') is not False:
        raise ValueError('invalid soundtrack receipt')
    result = json.loads(json.dumps(board))
    result.update(project_id=project_id, soundtrack=receipt, audio_sha256=receipt['audio_sha256'], audio_rights_confirmed=True)
    return json.loads(json.dumps(result))


def preview_timing(board, preview_path):
    """Use exactly the verified renderer's beat algorithm, not a fixed BPM guess."""
    from engines.media.render import beat_times, edges_for
    from engines.media.wave2 import snapshot_audio
    data, duration = snapshot_audio(preview_path, board['audio_sha256'])
    with tempfile.TemporaryDirectory() as td:
        staged = Path(td)/'preview.wav'
        staged.write_bytes(data)
        edges = edges_for(board, beat_times(staged))
    if edges[-1]/24 > duration or edges[-1]-edges[0] > 480:
        raise ValueError('timeline exceeds source or preview budget')
    return dict(start_frame=edges[0], cut_frames=[e-edges[0] for e in edges[1:-1]], frames=edges[-1]-edges[0])


def bind_timing(board, preview_path):
    """Freeze the reviewed timeline before issuing the project approval signature."""
    result = json.loads(json.dumps(board))
    result['approved_timing'] = preview_timing(result, preview_path)
    return result


def render_project(board, approval, master_key, project_id, source_path, preview_path,
                   image_paths, output, cache_root, *, evidence_paths=None):
    """Opt-in adapter to Wave 5. No automatic approval, external service or model."""
    from engines.creative.wave2 import verify
    from engines.media.incremental import render_incremental
    board = json.loads(json.dumps(board))
    key = project_key(master_key, project_id)
    if board.get('project_id') != project_id:
        raise ValueError('project mismatch')
    verify(board, approval, key)
    receipt = board['soundtrack']
    _review(receipt['provenance'], receipt['rights'])
    if receipt.get('version') != 'soundtrack-v1' or receipt.get('inference_verified') is not False:
        raise ValueError('invalid soundtrack receipt')
    if _sha(_read(source_path)) != receipt['source_sha256']:
        raise ValueError('original soundtrack changed')
    preview = _read(preview_path, 24_000_000)
    if _sha(preview) != receipt['audio_sha256'] or board['audio_sha256'] != receipt['audio_sha256']:
        raise ValueError('prepared soundtrack changed')
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    # Stage output privately until both visual QC and encoded soundtrack QC pass.
    with tempfile.TemporaryDirectory(dir=output.parent) as td:
        staged = Path(td)/'preview.wav'
        target = Path(td)/'result.mp4'
        staged.write_bytes(preview)
        timing = preview_timing(board, staged)
        if board.get('approved_timing') != timing:
            raise ValueError('reviewed timing missing or changed; renewed approval required')
        result = render_incremental(board, approval, key, image_paths, staged, target,
                                    project_cache(cache_root, master_key, project_id), evidence_paths=evidence_paths)
        if result['frames'] != timing['frames'] or result['cut_frames'] != timing['cut_frames']:
            raise ValueError('render timeline differs from preview')
        final = measure(target)
        # AAC and a selected beat interval can alter measured loudness; fail closed.
        if final['dbtp'] > -1.0 or final['lufs'] > -15.5:
            raise ValueError('encoded soundtrack exceeds loudness or peak limit')
        os.link(target, output)
    result.update(soundtrack=receipt, timing=timing, final_audio=final)
    return result
