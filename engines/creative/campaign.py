"""Local shot-aware campaign planning; observations never become factual ad copy."""
from itertools import permutations
from pathlib import Path

import numpy as np
from PIL import ImageOps

from engines.creative.wave2 import bounded_read, concepts, sha, validate
from engines.media.wave2 import snapshot_image

ROLES = ('hero', 'detail', 'context')
CAPTIONS = {
    'hero': 'Meet the product',
    'detail': 'Discover the details',
    'context': 'Explore the collection',
}
SEQUENCES = {
    'showcase': ('hero', 'detail', 'context'),
    'rhythm': ('detail', 'hero', 'context'),
    'occasion': ('context', 'hero', 'detail'),
    'explainer': ('hero', 'context', 'detail'),
}


def inspect_shot(path, product_id, role, source, *, rights_confirmed):
    if rights_confirmed is not True or role not in ROLES or not product_id.strip() or not source.strip():
        raise ValueError('reviewed shot identity, role and rights required')
    digest = sha(bounded_read(path, 20_000_000))
    image = snapshot_image(path, digest)
    gray = np.asarray(ImageOps.contain(image.convert('L'), (256, 256)), dtype=np.float32)
    sharpness = float(np.mean(np.abs(np.diff(gray, axis=0)))) if gray.shape[0] > 1 else 0.0
    return dict(path=str(Path(path)), product_id=product_id, role=role, source=source,
                rights_confirmed=True, asset_sha256=digest,
                pixel_sha256=sha(str(image.size).encode()+image.tobytes()),
                width=image.width, height=image.height, sharpness=round(sharpness, 3),
                luminance=round(float(gray.mean()), 2), semantic_status='human-labeled')


def recommend(brief, shots, ratio, *, collection=False):
    if ratio not in ('9:16', '16:9', '1:1') or not 3 <= len(shots) <= 8:
        raise ValueError('three to eight shots and a supported ratio required')
    if any(s.get('rights_confirmed') is not True or s.get('role') not in ROLES for s in shots):
        raise ValueError('unreviewed shot')
    if len({s['pixel_sha256'] for s in shots}) != len(shots):
        raise ValueError('duplicate decoded pixels')
    if not collection and len({s['product_id'] for s in shots}) != 1:
        raise ValueError('mixed products require explicit collection mode')
    results = []
    target = {'9:16': .5625, '16:9': 16/9, '1:1': 1}[ratio]
    for concept in concepts(brief):
        roles = SEQUENCES[concept['id']]
        candidates = []
        for chosen in permutations(shots, 3):
            if tuple(s['role'] for s in chosen) != roles:
                continue
            quality = sum(weight * (min(s['sharpness']/12, 1) + min(min(s['width'], s['height'])/720, 1)
                          + min(s['width']/s['height']/target, target/(s['width']/s['height'])))
                          for weight, s in zip((1.5, 1, 1), chosen))
            candidates.append((round(quality, 4), tuple(s['asset_sha256'] for s in chosen), chosen))
        if not candidates:
            continue
        quality, _, chosen = max(candidates, key=lambda x: (x[0], x[1]))
        results.append(dict(concept=concept['id'], score=round(concept['score']+quality, 4),
                            brief_score=concept['score'], shot_score=quality,
                            reasons=concept['reasons'], music=concept['music'], visual=concept['visual'],
                            roles=roles, shots=list(chosen)))
    if not results:
        raise ValueError('missing hero, detail or context shot')
    return sorted(results, key=lambda r: (-r['score'], r['concept']))


def campaign_board(brief, recommendation, ratio, audio_sha256, *, collection=False, audio_rights_confirmed=False):
    if audio_rights_confirmed is not True:
        raise ValueError('reviewed audio rights required')
    shots = recommendation['shots']
    # Reinspect source bytes and human labels before creating a signed board.
    checked = [inspect_shot(s['path'], s['product_id'], s['role'], s['source'],
                            rights_confirmed=s['rights_confirmed']) for s in shots]
    if checked != shots:
        raise ValueError('shot changed since recommendation')
    fresh = recommend(brief, checked, ratio, collection=collection)
    selected = next((r for r in fresh if r['concept'] == recommendation['concept']), None)
    if selected is None or selected['shots'] != shots:
        raise ValueError('invalid shot sequence')
    board = dict(version='m2-offline-v2', presentation='editorial-v1', ratio=ratio, fps=24,
                 brief=brief, concept=selected['concept'], audio_sha256=audio_sha256,
                 audio_rights_confirmed=True, campaign_mode='collection' if collection else 'single-product',
                 scenes=[dict(id=f'scene-{i+1}', beats=4, rights_confirmed=True,
                              asset_sha256=s['asset_sha256'], caption=CAPTIONS[s['role']],
                              shot_role=s['role'], product_id=s['product_id'], source=s['source'],
                              pixel_sha256=s['pixel_sha256']) for i, s in enumerate(shots)])
    validate(board)
    return board
