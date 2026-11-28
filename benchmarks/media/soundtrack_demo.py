"""Offline fixture-only demo. Original synthetic music and illustrations, no inference."""
import json
import secrets
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

from engines.creative.wave2 import approve, sha
from engines.media.soundtrack import bind_soundtrack, bind_timing, prepare, project_key, render_project
from engines.media.wave2 import HD


def main(directory):
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=False)
    rate = 44100
    t = np.arange(rate*15)/rate
    y = .18*np.sin(2*np.pi*220*t)*np.exp(-8*(t % .5))
    y += .48*np.sin(2*np.pi*880*t)*np.exp(-100*(t % .5))
    source = d/'original-fixture.wav'
    sf.write(source, np.column_stack((y, y*.8)), rate, subtype='FLOAT')
    data, receipt = prepare(source, dict(kind='synthetic-fixture', source_id='original rhythmic demo'),
                            dict(source=True, derivative=True, advertising_sync=True), 0, len(y))
    preview = d/'prepared.wav'
    preview.write_bytes(data)
    paths = []
    for i, (color, size) in enumerate(zip(('#dfccac', '#c9d4c7', '#c7b9b0'), (280, 340, 230))):
        im = Image.new('RGB', (900, 900), color)
        draw = ImageDraw.Draw(im)
        x, y, h = (450-size//2, 160, 540)
        draw.ellipse((x-30, y+h-20, x+size+30, y+h+60), fill='#807b6d')
        draw.rounded_rectangle((x, y, x+size, y+h), radius=36, fill='#243d38')
        draw.rounded_rectangle((x+size//4, y-55, x+3*size//4, y+40), radius=16, fill='#26332d')
        draw.rounded_rectangle((x+12, y+190, x+size-12, y+350), radius=8, fill='#e5d6b9')
        draw.text((450, y+270), 'AUREL DEMO', font=ImageFont.load_default(size=28), fill='#243d38', anchor='mm')
        path = d/f'shot-{i}.png'
        im.save(path)
        paths.append(path)
    key = secrets.token_bytes(32)
    brief = dict(audience='adults', occasion='evergreen', goal='awareness', industry='retail', emotion='calm', platform='reels')
    results = []
    for ratio in HD:
        board = dict(version='m2-offline-v2', presentation='editorial-v1', ratio=ratio, fps=24, brief=brief, concept='showcase',
                     scenes=[dict(id=f'scene-{i+1}', beats=4, rights_confirmed=True, asset_sha256=sha(p.read_bytes()), caption=c)
                             for i,(p,c) in enumerate(zip(paths, ('Meet the product', 'Discover the details', 'Explore the collection')))])
        board = bind_timing(bind_soundtrack(board, receipt, 'synthetic-demo'), preview)
        approval = approve(board, 'synthetic-fixture-reviewer', project_key(key, 'synthetic-demo'))
        name = ratio.replace(':', 'x')
        result = render_project(board, approval, key, 'synthetic-demo', source, preview, paths, d/(name+'.mp4'), d/'private-cache')
        results.append(result)
        print(json.dumps(result), flush=True)
    (d/'results.json').write_text(json.dumps(results, indent=2))


if __name__ == '__main__':
    main(sys.argv[1])
