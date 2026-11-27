"""Opt-in CPU scene regeneration; private trusted local workspace, not a service."""
import hashlib
import hmac
import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path

from PIL import __version__ as pillow_version

from engines.creative.wave2 import bounded_read, canonical, sha, verify
from engines.media import editorial, wave2
from engines.media.render import beat_times, edges_for

MAX_CLIP = 24 * 1024 * 1024
MAX_CACHE = 128 * 1024 * 1024
MAX_ENTRIES = 24


def _mac(key, payload):
    return hmac.new(key, b'synora-scene-cache-v1\0' + canonical(payload), hashlib.sha256).hexdigest()


def _engine_version():
    ffmpeg = subprocess.check_output(['ffmpeg', '-version'], timeout=10)
    return sha(ffmpeg + pillow_version.encode() + Path(__file__).read_bytes()
               + Path(editorial.__file__).read_bytes() + Path(wave2.__file__).read_bytes())


def scene_key(scene, size, presentation, index, frames, engine):
    return sha(canonical(dict(image=scene['asset_sha256'], caption=scene['caption'],
                              size=size, presentation=presentation, index=index,
                              frames=frames, fps=24, engine=engine)))


def _load(cache, identity, key, target):
    try:
        record = json.loads(bounded_read(cache / (identity+'.json'), 4096))
        payload = record['payload']
        if payload['identity'] != identity or not hmac.compare_digest(record['mac'], _mac(key, payload)):
            return False
        clip = bounded_read(cache / (identity+'.mp4'), MAX_CLIP)
        if sha(clip) != payload['sha256']:
            return False
        target.write_bytes(clip)
        return True
    except (OSError, ValueError, TypeError, KeyError):
        return False


def _atomic_write(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        staged = Path(f.name)
        f.write(data)
    try:
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def _save(cache, identity, key, target):
    # A full cache is bypassed, never silently evicted. Single trusted process only.
    clips = list(cache.glob('*.mp4'))
    size = target.stat().st_size
    old = cache / (identity+'.mp4')
    existing = old.stat().st_size if old.exists() else 0
    if (size > MAX_CLIP or (len(clips) >= MAX_ENTRIES and not old.exists())
            or sum(p.stat().st_size for p in clips)-existing+size > MAX_CACHE):
        return
    data = bounded_read(target, MAX_CLIP)
    payload = dict(identity=identity, sha256=sha(data))
    _atomic_write(old, data)
    _atomic_write(cache / (identity+'.json'), canonical(dict(payload=payload, mac=_mac(key, payload))))


def _encode(source, caption, size, frames, presentation, index, target):
    # Feed exactly one frame at a time; no raw-video spool or GPU.
    command = ['ffmpeg', '-nostdin', '-v', 'error', '-f', 'rawvideo', '-pixel_format', 'rgb24',
               '-video_size', f'{size[0]}x{size[1]}', '-framerate', '24', '-i', 'pipe:0',
               '-an', '-vf', 'scale=out_color_matrix=bt709', '-c:v', 'libx264', '-preset', 'fast',
               '-crf', '19', '-threads', '2', '-pix_fmt', 'yuv420p', '-colorspace', 'bt709',
               '-color_primaries', 'bt709', '-color_trc', 'bt709', '-video_track_timescale', '24000',
               '-bf', '0', '-g', '48', '-sc_threshold', '0', str(target)]
    with tempfile.TemporaryFile() as errors:
        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors) as proc:
            watchdog = threading.Timer(120, proc.kill)
            watchdog.start()
            try:
                assert proc.stdin is not None
                for n in range(frames):
                    progress = n/max(1, frames-1)
                    if presentation == 'editorial-v1':
                        frame, _ = editorial.editorial_layout(source, caption, size, progress, index)
                    else:
                        frame, _ = wave2.layout(source, caption, size, progress)
                    proc.stdin.write(frame.tobytes())
                proc.stdin.close()
                if proc.wait(timeout=20) != 0:
                    raise RuntimeError('scene encoding failed')
            finally:
                watchdog.cancel()
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()


def _probe(path):
    return json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(path)], timeout=20))['streams']


def render_incremental(board, approval, key, image_paths, audio_path, output, cache_dir, *, evidence_paths=None):
    # Check approval and all source evidence before touching any cached artifacts.
    board = json.loads(json.dumps(board))
    verify(board, approval, key)
    if len(image_paths) != 3:
        raise ValueError('three image paths required')
    evidence_paths = evidence_paths or {}
    for scene in board['scenes']:
        evidence = scene.get('evidence')
        if evidence is not None and (evidence['source_id'] not in evidence_paths or
                bounded_read(evidence_paths[evidence['source_id']], 4096) != evidence['text'].encode()):
            raise ValueError('claim source mismatch')
    images = [wave2.snapshot_image(p, s['asset_sha256']) for p, s in zip(image_paths, board['scenes'])]
    audio, duration = wave2.snapshot_audio(audio_path, board['audio_sha256'])
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    cache = Path(cache_dir)
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    if cache.is_symlink() or not cache.is_dir() or (os.name == 'posix' and cache.stat().st_mode & 0o077):
        raise ValueError('private cache directory required')
    size = wave2.HD[board['ratio']]
    engine = _engine_version()
    presentation = board.get('presentation', 'classic')
    hits = []
    rendered = []
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        wav = d/'audio.wav'
        wav.write_bytes(audio)
        edges = edges_for(board, beat_times(wav))
        count = edges[-1]-edges[0]
        if edges[-1]/24 > duration or count > 480:
            raise ValueError('timeline exceeds source or preview budget')
        for i, (scene, image) in enumerate(zip(board['scenes'], images)):
            frames = edges[i+1]-edges[i]
            identity = scene_key(scene, size, presentation, i, frames, engine)
            clip = d/f'scene-{i}.mp4'
            if _load(cache, identity, key, clip):
                hits.append(scene['id'])
            else:
                _encode(image, scene['caption'], size, frames, presentation, i, clip)
                streams = _probe(clip)
                if len(streams) != 1 or streams[0]['codec_name'] != 'h264' or int(streams[0]['nb_frames']) != frames:
                    raise ValueError('scene QC failed')
                subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(clip), '-f', 'null', '-'], check=True, timeout=120)
                _save(cache, identity, key, clip)
                rendered.append(scene['id'])
        concat = d/'list.txt'
        concat.write_text(''.join(f"file 'scene-{i}.mp4'\n" for i in range(3)))
        target = d/'output.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'concat', '-safe', '1', '-i', str(concat),
                        '-ss', str(edges[0]/24), '-i', str(wav), '-map', '0:v:0', '-map', '1:a:0', '-t', str(count/24),
                        '-c:v', 'copy', '-af', 'afade=t=in:d=0.05,afade=t=out:st='+str(max(0, count/24-.15))+':d=0.15',
                        '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(target)], check=True, timeout=120)
        streams = _probe(target)
        v = next(s for s in streams if s['codec_type'] == 'video')
        a = next(s for s in streams if s['codec_type'] == 'audio')
        if ((v['width'], v['height']) != size or v['codec_name'] != 'h264' or a['codec_name'] != 'aac'
                or int(v['nb_frames']) != count or abs(float(v['duration'])-count/24) > 1/24
                or abs(float(a['duration'])-count/24) > .1):
            raise ValueError('output QC failed')
        subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(target), '-f', 'null', '-'], check=True, timeout=120)
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as f:
            staged = Path(f.name)
            f.write(target.read_bytes())
        try:
            os.link(staged, output)
        finally:
            staged.unlink()
    return dict(ratio=board['ratio'], width=size[0], height=size[1], fps=24, frames=count, seconds=count/24,
                cut_frames=[e-edges[0] for e in edges[1:-1]], hits=hits, rendered=rendered,
                sha256=sha(output.read_bytes()), cache_bytes=sum(p.stat().st_size for p in cache.glob('*.mp4')),
                simulated=True)
