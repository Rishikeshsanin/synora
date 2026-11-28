"""Render a campaign, revise one approved caption, then reuse all clips."""
import copy
import json
import secrets
import sys
import time
from pathlib import Path

from engines.creative.campaign import campaign_board, inspect_shot, recommend
from engines.creative.wave2 import approve, sha
from engines.media.incremental import render_incremental


def main(manifest, audio, directory, ratio="9:16"):
    config = json.loads(Path(manifest).read_text())
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    shots = [inspect_shot(**s) for s in config['shots']]
    best = recommend(config['brief'], shots, ratio, collection=config['collection'])[0]
    original = campaign_board(config['brief'], best, ratio, sha(Path(audio).read_bytes()),
                              collection=config['collection'], audio_rights_confirmed=config['audio_rights_confirmed'])
    revised = copy.deepcopy(original)
    revised['scenes'][1]['caption'] = 'A closer look'
    key = secrets.token_bytes(32)
    rows = []
    for name, board in [('original', original), ('revised', revised), ('repeat', revised)]:
        approval = approve(board, 'offline-fixture-reviewer', key)
        start = time.monotonic()
        result = render_incremental(board, approval, key, [s['path'] for s in best['shots']], audio,
                                    d/(name+'.mp4'), d/'private-cache')
        result.update(name=name, wall_seconds=round(time.monotonic()-start, 3))
        rows.append(result)
        print(json.dumps(result), flush=True)
    assert [len(r['hits']) for r in rows] == [0, 2, 3]
    assert rows[1]['sha256'] == rows[2]['sha256']
    (d/'results.json').write_text(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main(*sys.argv[1:])
