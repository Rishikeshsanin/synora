import hashlib, json
from pathlib import Path
from PIL import Image, ImageOps


def inspect(path):
    p = Path(path)
    if p.stat().st_size > 20_000_000:
        raise ValueError('oversize asset')
    with Image.open(p) as im:
        if im.format not in ('PNG','JPEG','WEBP') or im.width*im.height > 16_000_000 or getattr(im,'n_frames',1)!=1:
            raise ValueError('unsupported asset')
        im = ImageOps.exif_transpose(im).convert('RGB')
        q = im.resize((64,64)).quantize(colors=4)
        palette = q.getpalette()
        return dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(), width=im.width, height=im.height,
                    palette=[palette[i*3:i*3+3] for _,i in sorted(q.getcolors(),reverse=True)], semantic_status='unverified')


def rank(brief):
    keys=('audience','occasion','goal','industry','emotion','platform')
    if any(not isinstance(brief.get(k),str) or not brief[k].strip() for k in keys):
        raise ValueError('incomplete brief')
    a,o,g,i,e,p=(brief[k].lower() for k in keys)
    rows=[('showcase','minimal instrumental',3+2*(g=='awareness')+(i=='retail')+(e=='calm')),
          ('rhythm','upbeat instrumental',3+2*(p in ('reels','shorts','tiktok'))+(a=='young adults')+(e=='excited')),
          ('occasion','warm instrumental',3+2*(o!='evergreen')+(g=='engagement')+(e=='warm'))]
    return [dict(id=k,music=m,score=s,method='heuristic-v1') for k,m,s in sorted(rows,key=lambda r:(-r[2],r[0]))]


def digest(board):
    return hashlib.sha256(json.dumps(board,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def storyboard(brief, concept, assets, captions):
    if concept not in {r['id'] for r in rank(brief)} or len(assets)!=3 or len(captions)!=3:
        raise ValueError('invalid concept or scene count')
    for a,c in zip(assets,captions):
        if a.get('rights_confirmed') is not True or not isinstance(c,str) or not c.strip() or len(c)>64 or not c.isascii() or not c.isprintable():
            raise ValueError('rights or caption invalid')
    return dict(version='m2-proposal-1',brief=brief,concept=concept,fps=24,scenes=[dict(id=f'scene-{n+1}',asset=a,caption=c,beats=4) for n,(a,c) in enumerate(zip(assets,captions))])
