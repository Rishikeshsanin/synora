"""Deterministic editorial treatment; only approved captions become ad copy."""
import math
from PIL import Image, ImageDraw, ImageFont, ImageOps


def editorial_layout(source, caption, size, progress, scene):
    if scene not in (0, 1, 2) or not 0 <= progress <= 1:
        raise ValueError('invalid shot')
    w, h = size
    u = min(size)
    margin = round(u * .07)
    wide = w > h
    colors = [('#211b18', '#e6bc8c'), ('#e9ddcc', '#633b27'), ('#30251f', '#f3ce9d')]
    bg, fg = colors[scene]
    frame = Image.new('RGB', size, bg)
    draw = ImageDraw.Draw(frame)
    # Distinct editorial split, framed detail and closing card; source never cropped.
    if wide:
        if scene == 1:
            area = (margin, margin, round(w * .53), h - margin)
            text = (round(w * .60), margin, w - margin, h - margin)
        else:
            area = (round(w * .45), margin, w - margin, h - margin)
            text = (margin, margin, round(w * .40), h - margin)
    else:
        if scene == 1:
            area = (margin, round(h * .29), w - margin, round(h * .91))
            text = (margin, margin, w - margin, round(h * .26))
        else:
            area = (margin, round(h * .08), w - margin, round(h * .67))
            text = (margin, round(h * .70), w - margin, h - margin)
    ax, ay, bx, by = area
    scale = .96 + .04 * (1 - math.cos(math.pi * progress)) / 2
    photo = ImageOps.contain(source, (round((bx-ax)*scale), round((by-ay)*scale)), Image.Resampling.LANCZOS)
    x = ax + (bx-ax-photo.width)//2
    y = ay + (by-ay-photo.height)//2
    draw.rectangle((x-5, y-5, x+photo.width+4, y+photo.height+4), fill=fg)
    frame.paste(photo, (x, y))
    tx, ty, ex, ey = text
    tw = ex-tx
    th = ey-ty
    number = ImageFont.load_default(size=round(u*.026))
    draw.text((tx, ty), f'0{scene+1} / 03', fill=fg, font=number, anchor='lt')
    line_y = ty+round(u*.045)
    draw.line((tx, line_y, ex, line_y), fill=fg, width=2)
    # Fit exact approved copy without truncation or invented marketing statements.
    for fs in range(round(u*.083), round(u*.028)-1, -2):
        font = ImageFont.load_default(size=fs)
        lines = ['']
        for word in caption.split():
            trial = (lines[-1]+' '+word).strip()
            if draw.textlength(trial, font=font) <= tw-24:
                lines[-1] = trial
            else:
                lines.append(word)
        copy = '\n'.join(lines)
        box = draw.multiline_textbbox((0, 0), copy, font=font, spacing=8)
        if len(lines) <= 3 and all(lines) and box[2]-box[0] <= tw-24 and box[3]-box[1] <= th-round(u*.085):
            break
    else:
        raise ValueError('approved caption does not fit editorial treatment')
    cy = (line_y+ey)//2
    if scene == 2:
        # CTA treatment is visual only; caption remains exactly the reviewed text.
        draw.rounded_rectangle((tx, line_y+12, ex, ey), radius=12, outline=fg, width=3)
    draw.multiline_text(((tx+ex)//2, cy), copy, fill=fg, font=font, anchor='mm', align='center', spacing=8)
    return frame, (x, y, photo.width, photo.height)
