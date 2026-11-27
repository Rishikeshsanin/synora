"""Offline multi-shot demonstration from explicitly reviewed fixture files."""
import json
import secrets
import sys
from pathlib import Path

from engines.creative.campaign import campaign_board, inspect_shot, recommend
from engines.creative.wave2 import approve, sha
from engines.media.wave2 import HD, render_hd


def main(manifest, audio, directory):
    config = json.loads(Path(manifest).read_text())
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    shots = [inspect_shot(**s) for s in config['shots']]
    key = secrets.token_bytes(32)
    audio_digest = sha(Path(audio).read_bytes())
    results = []
    for ratio in HD:
        ranked = recommend(config['brief'], shots, ratio, collection=config['collection'])
        best = ranked[0]
        board = campaign_board(config['brief'], best, ratio, audio_digest, collection=config['collection'], audio_rights_confirmed=config.get('audio_rights_confirmed'))
        approval = approve(board, 'offline-fixture-reviewer', key)
        name = ratio.replace(':', 'x')
        (d/(name+'.board.json')).write_text(json.dumps(board, indent=2))
        (d/(name+'.recommendations.json')).write_text(json.dumps(ranked, indent=2))
        result = render_hd(board, approval, key, [s['path'] for s in best['shots']], audio, d/(name+'.mp4'))
        results.append(result)
        print(json.dumps(result), flush=True)
    (d/'results.json').write_text(json.dumps(results, indent=2))


if __name__ == '__main__':
    main(*sys.argv[1:])
