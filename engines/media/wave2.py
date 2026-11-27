"""Trusted local HD renderer. No production authorization or external providers."""
import io
import json
import math
import os
import subprocess
import tempfile
import wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from engines.creative.wave2 import bounded_read, sha, verify
from engines.media.render import beat_times, edges_for
from engines.media.editorial import editorial_layout

HD = {'9:16': (1080,1920), '16:9': (1920,1080), '1:1': (1080,1080)}


def snapshot_image(path, expected):
    data = bounded_read(path, 20_000_000)
    if sha(data) != expected:
        raise ValueError('asset hash mismatch')
    with Image.open(io.BytesIO(data)) as im:
        if im.format not in ('PNG','JPEG','WEBP') or im.width*im.height > 16_000_000 or getattr(im,'n_frames',1) != 1:
            raise ValueError('unsupported image')
        return ImageOps.exif_transpose(im).convert('RGB')


def snapshot_audio(path, expected):
    data = bounded_read(path, 24_000_000)
    if sha(data) != expected:
        raise ValueError('audio hash mismatch')
    with wave.open(io.BytesIO(data)) as f:
        if f.getsampwidth() != 2 or not 1 <= f.getnchannels() <= 2 or not 8000 <= f.getframerate() <= 48000:
            raise ValueError('unsupported PCM audio')
        duration = f.getnframes()/f.getframerate()
        if not 3 <= duration <= 60 or len(f.readframes(f.getnframes())) != f.getnframes()*f.getnchannels()*2:
            raise ValueError('invalid audio duration or payload')
    return data, duration


def layout(source, caption, size, progress):
    w,h = size
    u=min(w,h)
    margin=round(u*.08)
    top=round(h*.12)
    bottom=round(h*.25)
    frame=Image.new('RGB',size,'#101d28')
    draw=ImageDraw.Draw(frame)
    small=ImageFont.load_default(size=round(u*.028))
    font=ImageFont.load_default(size=round(u*.052))
    draw.text((margin,round(h*.055)),'PRODUCT STUDY',font=small,fill='#b7c9c7',anchor='lm')
    scale=.96+.04*(1-math.cos(math.pi*progress))/2
    photo=ImageOps.contain(source,(round((w-2*margin)*scale),round((h-top-bottom)*scale)),Image.Resampling.LANCZOS)
    x=(w-photo.width)//2
    y=top+(h-top-bottom-photo.height)//2
    frame.paste(photo,(x,y))
    # Product pixels are untouched except orientation and proportional resampling.
    words=caption.split()
    lines=['']
    for word in words:
        attempt=(lines[-1]+' '+word).strip()
        if draw.textlength(attempt,font=font)>w-2*margin:
            lines.append(word)
        else:
            lines[-1]=attempt
    if len(lines)>2 or any(not s or draw.textlength(s,font=font)>w-2*margin for s in lines):
        raise ValueError('caption does not fit safe area')
    draw.multiline_text((w//2,h-round(bottom*.54)),'\n'.join(lines),font=font,fill='white',anchor='mm',align='center',spacing=8)
    draw.rounded_rectangle((margin,h-round(h*.06),w-margin,h-round(h*.055)),radius=3,fill='#334653')
    draw.rounded_rectangle((margin,h-round(h*.06),margin+max(1,round((w-2*margin)*progress)),h-round(h*.055)),radius=3,fill='#d4b586')
    return frame,(x,y,photo.width,photo.height)


def render_hd(board, approval, key, image_paths, audio_path, output, *, evidence_paths=None):
    verify(board,approval,key)
    # Freeze reviewed data before decoding; paths are supplied by trusted caller, not board.
    board=json.loads(json.dumps(board))
    verify(board,approval,key)
    if len(image_paths)!=3:
        raise ValueError('three image paths required')
    evidence_paths=evidence_paths or {}
    for scene in board['scenes']:
        e=scene.get('evidence')
        if e is not None:
            if e['source_id'] not in evidence_paths or bounded_read(evidence_paths[e['source_id']],4096)!=e['text'].encode():
                raise ValueError('claim source mismatch')
    images=[snapshot_image(p,s['asset_sha256']) for p,s in zip(image_paths,board['scenes'])]
    audio,duration=snapshot_audio(audio_path,board['audio_sha256'])
    output=Path(output)
    size=HD[board['ratio']]
    if output.exists():
        raise FileExistsError(output)
    with tempfile.TemporaryDirectory() as td:
        d=Path(td)
        wav=d/'audio.wav'
        wav.write_bytes(audio)
        edges=edges_for(board,beat_times(wav))
        count=edges[-1]-edges[0]
        if edges[-1]/24>duration or count>480:
            raise ValueError('timeline exceeds source or preview budget')
        # Render one scene at a time; encode JPEG-free raw RGB through a bounded on-disk stream.
        raw=d/'frames.rgb'
        with raw.open('wb') as f:
            for i,(source,s) in enumerate(zip(images,board['scenes'])):
                nframes=edges[i+1]-edges[i]
                for n in range(nframes):
                    progress=n/max(1,nframes-1)
                    if board.get('presentation') == 'editorial-v1':
                        frame,_=editorial_layout(source,s['caption'],size,progress,i)
                    else:
                        frame,_=layout(source,s['caption'],size,progress)
                    f.write(frame.tobytes())
        target=d/'result.mp4'
        subprocess.run(['ffmpeg','-nostdin','-v','error','-f','rawvideo','-pixel_format','rgb24','-video_size',f'{size[0]}x{size[1]}','-framerate','24','-i',str(raw),'-ss',str(edges[0]/24),'-i',str(wav),'-map','0:v:0','-map','1:a:0','-t',str(count/24),'-c:v','libx264','-preset','fast','-crf','19','-threads','2','-pix_fmt','yuv420p','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','-vf','scale=out_color_matrix=bt709','-af','afade=t=in:d=0.05,afade=t=out:st='+str(max(0,count/24-.15))+':d=0.15','-c:a','aac','-b:a','192k','-movflags','+faststart',str(target)],check=True,timeout=180)
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(target)],timeout=20))
        v=next(s for s in probe['streams'] if s['codec_type']=='video')
        a=next(s for s in probe['streams'] if s['codec_type']=='audio')
        if (v['width'],v['height'])!=size or v['codec_name']!='h264' or a['codec_name']!='aac' or int(v['nb_frames'])!=count or abs(float(a['duration'])-count/24)>.1:
            raise ValueError('output QC failed')
        subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(target),'-f','null','-'],check=True,timeout=120)
        # Same-filesystem publication, exclusive link avoids overwriting another render.
        with tempfile.NamedTemporaryFile(dir=output.parent,delete=False) as f:
            staged=Path(f.name)
            f.write(target.read_bytes())
        try:
            os.link(staged,output)
        finally:
            staged.unlink()
    return dict(ratio=board['ratio'],width=size[0],height=size[1],frames=count,seconds=count/24,cut_frames=[e-edges[0] for e in edges[1:-1]],sha256=sha(output.read_bytes()),simulated=True)
