"""Generate original fictional product assets and an original synthetic soundtrack."""
import json
import secrets
import sys
import time
import wave
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from engines.creative.wave2 import approve, concepts, sha
from engines.media.wave2 import HD, render_hd


def main(directory):
    d=Path(directory)
    d.mkdir(parents=True,exist_ok=True)
    paths=[]
    for i,bg in enumerate(('#d8c4a4','#a4c6bd','#b9b5cc')):
        p=d/f'product-{i}.png'
        im=Image.new('RGB',(1200,900),bg)
        draw=ImageDraw.Draw(im)
        draw.ellipse((270,770,930,845),fill='#66716d')
        draw.rounded_rectangle((410,205,790,790),radius=72,fill='#193b40')
        draw.rounded_rectangle((475,110,725,245),radius=20,fill='#142b30')
        draw.rounded_rectangle((433,380,767,610),radius=12,fill='#e9dfc9')
        font=ImageFont.load_default(size=48)
        draw.text((600,465),'AUREL',font=font,anchor='mm',fill='#193b40')
        draw.text((600,525),'DEMO',font=ImageFont.load_default(size=25),anchor='mm',fill='#193b40')
        im.save(p)
        paths.append(p)
    audio=d/'original.wav'
    sr=22050
    y=np.zeros(sr*10,dtype=np.float32)
    for n in range(20):
        start=n*sr//2
        t=np.arange(sr//2)/sr
        click=.48*np.sin(2*np.pi*880*t)*np.exp(-t*100)
        chord=sum(np.sin(2*np.pi*f*t) for f in (130.81,164.81,196.00))*.035*np.exp(-t*5)
        y[start:start+len(t)]=click+chord
    with wave.open(str(audio),'wb') as f:
        f.setparams((1,2,sr,0,'NONE','not compressed'))
        f.writeframes((y*32767).astype('<i2').tobytes())
    brief=dict(audience='young adults',occasion='launch',goal='awareness',industry='retail',emotion='excited',platform='reels')
    source=d/'verified-label.txt'
    source.write_bytes(b'AUREL DEMO')
    evidence=dict(source_id='fixture-label',text='AUREL DEMO',sha256=sha(source.read_bytes()),reviewed=True)
    key=secrets.token_bytes(32)
    results=[]
    for ratio in HD:
        board=dict(version='m2-offline-v2',ratio=ratio,fps=24,brief=brief,concept=concepts(brief)[0]['id'],audio_sha256=sha(audio.read_bytes()),audio_rights_confirmed=True,scenes=[dict(id=f'scene-{i+1}',beats=4,rights_confirmed=True,asset_sha256=sha(p.read_bytes()),caption=c,evidence=evidence if i==0 else None) for i,(p,c) in enumerate(zip(paths,['AUREL DEMO','Discover the details','Explore the collection']))])
        approval=approve(board,'synthetic-demo-reviewer',key)
        (d/(ratio.replace(':','x')+'.board.json')).write_text(json.dumps(board,indent=2))
        start=time.monotonic()
        result=render_hd(board,approval,key,paths,audio,d/(ratio.replace(':','x')+'.mp4'),evidence_paths={'fixture-label':source})
        result['wall_seconds']=round(time.monotonic()-start,2)
        results.append(result)
        print(json.dumps(result),flush=True)
    (d/'results.json').write_text(json.dumps(results,indent=2))


if __name__=='__main__':
    main(sys.argv[1])
