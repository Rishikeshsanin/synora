import json, subprocess, sys, time, wave
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from engines.creative.planner import inspect, rank, storyboard, digest
from engines.media.render import render, SIZES


def main(directory):
    d=Path(directory); d.mkdir(parents=True,exist_ok=True); assets=[]
    for i,color in enumerate(('#b5a789','#78a5a3','#c1a1a0')):
        p=d/f'fixture-{i}.png'; im=Image.new('RGB',(600,400),color); draw=ImageDraw.Draw(im)
        draw.rounded_rectangle((230,75,370,345),radius=24,fill='#193a43'); draw.rectangle((255,45,345,90),fill='#193a43'); draw.rectangle((245,165,355,235),fill='white'); draw.text((270,190),'DEMO',fill='black'); im.save(p)
        assets.append(dict(path=str(p.resolve()),rights_confirmed=True,**inspect(p)))
    audio=d/'clicks.wav'; sr=22050; y=np.zeros(sr*10,dtype=np.float32)
    for n in range(20):
        start=n*sr//2; t=np.arange(1100)/sr; y[start:start+1100]=.5*np.sin(2*np.pi*880*t)*np.exp(-t*100)
    with wave.open(str(audio),'wb') as f:
        f.setparams((1,2,sr,0,'NONE','not compressed')); f.writeframes((y*32767).astype('<i2').tobytes())
    brief=dict(audience='young adults',occasion='evergreen',goal='awareness',industry='retail',emotion='excited',platform='reels')
    board=storyboard(brief,rank(brief)[0]['id'],assets,['Meet DEMO','A closer look','Explore the collection']); approval=digest(board)
    (d/'board.json').write_text(json.dumps(board,indent=2)); (d/'approval.txt').write_text(approval+'\n'); results=[]
    for ratio,size in SIZES.items():
        p=d/(ratio.replace(':','x')+'.mp4'); start=time.monotonic(); r=render(board,approval,audio,ratio,p)
        info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)])); v=next(s for s in info['streams'] if s['codec_type']=='video'); a=next(s for s in info['streams'] if s['codec_type']=='audio')
        assert (v['width'],v['height'])==size and v['codec_name']=='h264' and a['codec_name']=='aac' and int(v['nb_frames'])==r['frames']
        r.update(seconds=float(info['format']['duration']),bytes=p.stat().st_size,wall_seconds=round(time.monotonic()-start,2)); results.append(r)
    (d/'results.json').write_text(json.dumps(results,indent=2)); print(json.dumps(results,indent=2))


if __name__=='__main__': main(sys.argv[1])
