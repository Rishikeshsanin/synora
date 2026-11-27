"""Offline proposal: deterministic concept explanations and signed review bundles."""
import hashlib
import hmac
import json
import time
from pathlib import Path

NEUTRAL = ('A closer look', 'Explore the collection', 'Discover the details', 'Meet the product')
RATIOS = ('9:16', '16:9', '1:1')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def bounded_read(path, cap):
    with Path(path).open('rb') as f:
        data = f.read(cap + 1)
    if not data or len(data) > cap:
        raise ValueError('empty or oversized source')
    return data


def concepts(brief):
    keys = ('audience', 'occasion', 'goal', 'industry', 'emotion', 'platform')
    if any(not isinstance(brief.get(k), str) or not brief[k].strip() or len(brief[k]) > 100 for k in keys):
        raise ValueError('invalid brief')
    b = {k: brief[k].strip().casefold() for k in keys}
    templates = [
        ('showcase', 'Minimal instrumental', 'Editorial product spotlight', {'goal': ('awareness','conversion'), 'industry': ('retail','luxury'), 'emotion': ('calm','premium')}),
        ('rhythm', 'Upbeat instrumental', 'Rhythmic product details', {'platform': ('reels','shorts','tiktok'), 'audience': ('young adults','students'), 'emotion': ('excited','energetic')}),
        ('occasion', 'Warm instrumental', 'Occasion-led reveal', {'occasion': ('festival','birthday','holiday','launch'), 'goal': ('engagement',), 'emotion': ('warm','joyful')}),
        ('explainer', 'Neutral ambient instrumental', 'Sequential feature presentation', {'goal': ('education','consideration'), 'industry': ('technology','services'), 'audience': ('professionals','businesses')})]
    rows = []
    for name, music, visual, matches in templates:
        reasons = [f'{k}: {b[k]}' for k, terms in matches.items() if b[k] in terms]
        score = 3 + sum(2 if x.split(':')[0] in ('goal','platform','occasion') else 1 for x in reasons)
        rows.append(dict(id=name, score=score, reasons=reasons, music=music, visual=visual, method='heuristic-v2'))
    return sorted(rows, key=lambda x: (-x['score'], x['id']))


def validate(board):
    if board.get('version') != 'm2-offline-v2' or board.get('ratio') not in RATIOS or board.get('fps') != 24:
        raise ValueError('unsupported board')
    if board.get('presentation', 'classic') not in ('classic', 'editorial-v1'):
        raise ValueError('unsupported presentation')
    if board.get('concept') not in {c['id'] for c in concepts(board['brief'])}:
        raise ValueError('unknown concept')
    if not isinstance(board.get('scenes'), list) or len(board['scenes']) != 3:
        raise ValueError('three scenes required')
    for i, scene in enumerate(board['scenes']):
        if scene.get('id') != f'scene-{i+1}' or scene.get('beats') != 4 or scene.get('rights_confirmed') is not True:
            raise ValueError('invalid scene or rights')
        caption = scene.get('caption')
        if not isinstance(caption, str) or not caption.isascii() or not caption.isprintable() or not 1 <= len(caption) <= 90:
            raise ValueError('invalid caption')
        evidence = scene.get('evidence')
        if evidence is None:
            if caption not in NEUTRAL:
                raise ValueError('unsubstantiated caption')
        elif (not isinstance(evidence, dict) or evidence.get('reviewed') is not True or evidence.get('text') != caption
              or not evidence.get('source_id') or evidence.get('sha256') != sha(caption.encode())):
            raise ValueError('claim evidence mismatch')
        if not isinstance(scene.get('asset_sha256'), str) or len(scene['asset_sha256']) != 64:
            raise ValueError('invalid asset hash')
    if board.get('audio_rights_confirmed') is not True or not isinstance(board.get('audio_sha256'), str) or len(board['audio_sha256']) != 64:
        raise ValueError('invalid audio rights or hash')


def approve(board, reviewer, key, *, now=None, ttl=3600):
    validate(board)
    if not isinstance(key, bytes) or len(key) < 32 or not isinstance(reviewer, str) or not reviewer.strip() or not 1 <= ttl <= 3600:
        raise ValueError('invalid trusted approval inputs')
    issued = int(time.time() if now is None else now)
    payload = dict(board_sha256=sha(canonical(board)), reviewer=reviewer, issued=issued, expires=issued+ttl)
    return dict(payload=payload, signature=hmac.new(key, canonical(payload), hashlib.sha256).hexdigest())


def verify(board, approval, key, *, now=None):
    validate(board)
    if not isinstance(key, bytes) or len(key) < 32:
        raise ValueError('invalid trusted approval key')
    p = approval['payload']
    expected = hmac.new(key, canonical(p), hashlib.sha256).hexdigest()
    t = int(time.time() if now is None else now)
    if (not hmac.compare_digest(expected, approval['signature']) or p['board_sha256'] != sha(canonical(board))
        or not p['issued'] <= t < p['expires'] or not 1 <= p['expires']-p['issued'] <= 3600):
        raise ValueError('invalid or expired approval')
