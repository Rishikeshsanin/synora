import json
import subprocess
import tempfile
import shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
import numpy as np
from engines.creative.planner import digest, inspect

SIZES={'9:16':(360,640),'16:9':(640,360),'1:1':(480,480)}


def beat_times(audio):
    import librosa
    y,sr=librosa.load(audio,sr=22050,mono=True,duration=60)
    if not len(y) or np.max(np.abs(y))<.001:
        raise ValueError('silent soundtrack')
    _,frames=librosa.beat.beat_track(y=y,sr=sr,trim=False)
    return librosa.frames_to_time(frames,sr=sr).tolist()


def edges_for(board,times):
    if board['fps']!=24 or len(board['scenes'])!=3 or any(s['beats']!=4 for s in board['scenes']) or len(times)<13:
        raise ValueError('unsupported timeline')
    edges=[round(times[i]*24) for i in (0,4,8,12)]
    if edges[0]<0 or edges[-1]>1440 or any(b-a<24 for a,b in zip(edges,edges[1:])):
        raise ValueError('invalid beat timing')
    return edges


def render(board,approval,audio,ratio,output):
    if approval!=digest(board):
        raise ValueError('approval mismatch')
    w,h=SIZES[ratio]
    output=Path(output)
    if output.exists():
        raise FileExistsError(output)
    edges=edges_for(board,beat_times(audio))
    count=0
    font=ImageFont.load_default(size=18)
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp)
        for i,s in enumerate(board['scenes']):
            a=s['asset']
            c=s['caption']
            p=Path(a['path'])
            if a.get('rights_confirmed') is not True or inspect(p)['sha256']!=a['sha256']:
                raise ValueError('unapproved asset')
            if not isinstance(c,str) or not c.strip() or len(c)>64 or not c.isascii() or not c.isprintable():
                raise ValueError('invalid caption')
            with Image.open(p) as im:
                source=ImageOps.exif_transpose(im).convert('RGB')
            duration=edges[i+1]-edges[i]
            for n in range(duration):
                frame=Image.new('RGB',(w,h),'#101c28')
                scale=.94+.06*n/max(1,duration-1)
                photo=ImageOps.contain(source,(int((w-48)*scale),int((h-112)*scale)))
                frame.paste(photo,((w-photo.width)//2,(h-64-photo.height)//2))
                draw=ImageDraw.Draw(frame)
                if draw.textlength(c,font=font)>w-32:
                    raise ValueError('caption too wide')
                draw.text((w//2,h-40),c,fill='white',font=font,anchor='mm')
                frame.save(tmp/f'{count:05d}.png')
                count+=1
        target=tmp/'render.mp4'
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-framerate','24','-i',str(tmp/'%05d.png'),'-ss',str(edges[0]/24),'-i',str(Path(audio).resolve()),'-map','0:v:0','-map','1:a:0','-t',str(count/24),'-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(target)],check=True,timeout=120)
        with output.open('xb') as dst,target.open('rb') as src:
            shutil.copyfileobj(src,dst)
    return dict(ratio=ratio,width=w,height=h,fps=24,frames=count,cut_frames=[e-edges[0] for e in edges[1:-1]],simulated=True)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('board')
    p.add_argument('approval')
    p.add_argument('audio')
    p.add_argument('ratio',choices=SIZES)
    p.add_argument('output')
    a=p.parse_args()
    print(json.dumps(render(json.loads(Path(a.board).read_text()),a.approval,a.audio,a.ratio,a.output)))
