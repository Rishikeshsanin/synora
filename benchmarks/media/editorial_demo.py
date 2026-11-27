"""Offline A/B preview from an explicitly rights-cleared caller-provided photo."""
import json
import secrets
import sys
import time
from pathlib import Path
from engines.creative.wave2 import approve, sha
from engines.media.wave2 import HD, render_hd


def main(photo, audio, directory):
    photo, audio, d = Path(photo), Path(audio), Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    brief = dict(audience='adults', occasion='evergreen', goal='awareness', industry='retail', emotion='calm', platform='reels')
    results = []
    for ratio in HD:
        for presentation in ('classic', 'editorial-v1'):
            board = dict(version='m2-offline-v2', presentation=presentation, ratio=ratio, fps=24, brief=brief, concept='showcase', audio_sha256=sha(audio.read_bytes()), audio_rights_confirmed=True, scenes=[dict(id=f'scene-{i+1}', beats=4, rights_confirmed=True, asset_sha256=sha(photo.read_bytes()), caption=c) for i,c in enumerate(('Meet the product','Discover the details','Explore the collection'))])
            start = time.monotonic()
            approval = approve(board,'offline-demo-reviewer',key)
            name = ratio.replace(':','x')+'-'+presentation
            (d/(name+'.board.json')).write_text(json.dumps(board,indent=2))
            result = render_hd(board,approval,key,[photo]*3,audio,d/(name+'.mp4'))
            result.update(presentation=presentation, wall_seconds=round(time.monotonic()-start,2))
            results.append(result)
            print(json.dumps(result),flush=True)
    (d/'results.json').write_text(json.dumps(results,indent=2))


if __name__ == '__main__':
    main(*sys.argv[1:])
