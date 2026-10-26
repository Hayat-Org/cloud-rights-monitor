"""
Line illustrations used as large watermarks on photo-less cards, one per category.

They are drawn with Pillow primitives (no image files, no licences). Every glyph takes the
same arguments - (draw, cx, cy, r, color) - and stays inside a square of half-size `r`
around its centre, so they can be swapped freely.
"""
from services import card_design as d


def _w(r: int) -> int:
    return max(3, r // 9)


def scales(draw, cx, cy, r, color):
    w = _w(r)
    beam_y = cy - int(r * 0.62)
    draw.line((cx, cy - r, cx, cy + r), fill=color, width=w)                      # stand
    draw.line((cx - int(r * 0.55), cy + r, cx + int(r * 0.55), cy + r), fill=color, width=w)  # base
    draw.line((cx - int(r * 0.74), beam_y, cx + int(r * 0.74), beam_y), fill=color, width=w)  # beam
    for side in (-1, 1):
        px = cx + side * int(r * 0.70)
        pan_y = beam_y + int(r * 0.8)
        rad = int(r * 0.28)
        draw.line((px, beam_y, px - rad, pan_y), fill=color, width=max(2, w // 2))
        draw.line((px, beam_y, px + rad, pan_y), fill=color, width=max(2, w // 2))
        draw.arc((px - rad, pan_y - int(rad * 0.55), px + rad, pan_y + int(rad * 0.55)), 0, 180, fill=color, width=w)


def camera(draw, cx, cy, r, color):
    w = _w(r)
    draw.rounded_rectangle((cx - r, cy - int(r * 0.55), cx + r, cy + int(r * 0.75)), radius=int(r * 0.18), outline=color, width=w)
    draw.rounded_rectangle((cx - int(r * 0.35), cy - int(r * 0.85), cx + int(r * 0.3), cy - int(r * 0.55)), radius=int(r * 0.08), outline=color, width=w)
    lens = int(r * 0.45)
    draw.ellipse((cx - lens, cy + int(r * 0.1) - lens, cx + lens, cy + int(r * 0.1) + lens), outline=color, width=w)
    inner = int(r * 0.2)
    draw.ellipse((cx - inner, cy + int(r * 0.1) - inner, cx + inner, cy + int(r * 0.1) + inner), outline=color, width=max(2, w // 2))


def bars(draw, cx, cy, r, color):
    w = _w(r)
    draw.rounded_rectangle((cx - int(r * 0.85), cy - r, cx + int(r * 0.85), cy + r), radius=int(r * 0.25), outline=color, width=w)
    for k in (-1.5, -0.5, 0.5, 1.5):
        x = cx + int(k * r * 0.42)
        draw.line((x, cy - r, x, cy + r), fill=color, width=w)


def alert(draw, cx, cy, r, color):
    w = _w(r)
    pts = [(cx, cy - r), (cx + int(r * 0.98), cy + int(r * 0.78)), (cx - int(r * 0.98), cy + int(r * 0.78))]
    draw.line(pts + [pts[0]], fill=color, width=w, joint="curve")
    draw.line((cx, cy - int(r * 0.3), cx, cy + int(r * 0.2)), fill=color, width=w)
    dot = max(3, w)
    draw.ellipse((cx - dot, cy + int(r * 0.42) - dot, cx + dot, cy + int(r * 0.42) + dot), fill=color)


def pin(draw, cx, cy, r, color):
    w = _w(r)
    top = int(r * 0.58)
    head_y = cy - int(r * 0.32)
    draw.arc((cx - top, head_y - top, cx + top, head_y + top), 150, 390, fill=color, width=w)
    draw.line((cx - int(top * 0.87), head_y + int(top * 0.5), cx, cy + r), fill=color, width=w)
    draw.line((cx + int(top * 0.87), head_y + int(top * 0.5), cx, cy + r), fill=color, width=w)
    dot = int(r * 0.2)
    draw.ellipse((cx - dot, head_y - dot, cx + dot, head_y + dot), outline=color, width=max(2, w // 2))


def venus(draw, cx, cy, r, color):
    w = _w(r)
    rad = int(r * 0.58)
    cy0 = cy - int(r * 0.35)
    draw.ellipse((cx - rad, cy0 - rad, cx + rad, cy0 + rad), outline=color, width=w)
    draw.line((cx, cy0 + rad, cx, cy + r), fill=color, width=w)
    draw.line((cx - int(r * 0.38), cy + int(r * 0.62), cx + int(r * 0.38), cy + int(r * 0.62)), fill=color, width=w)


def eye(draw, cx, cy, r, color):
    w = _w(r)
    steps = 40
    top, bottom = [], []
    for i in range(steps + 1):
        t = -1 + 2 * i / steps
        x = cx + int(r * t)
        dy = int(r * 0.62 * (1 - t * t))
        top.append((x, cy - dy))
        bottom.append((x, cy + dy))
    draw.line(top, fill=color, width=w, joint="curve")
    draw.line(bottom, fill=color, width=w, joint="curve")
    iris = int(r * 0.34)
    draw.ellipse((cx - iris, cy - iris, cx + iris, cy + iris), outline=color, width=w)
    pupil = int(r * 0.13)
    draw.ellipse((cx - pupil, cy - pupil, cx + pupil, cy + pupil), fill=color)


def ballot(draw, cx, cy, r, color):
    w = _w(r)
    draw.rounded_rectangle((cx - r, cy, cx + r, cy + r), radius=int(r * 0.12), outline=color, width=w)
    draw.line((cx - int(r * 0.5), cy + int(r * 0.28), cx + int(r * 0.5), cy + int(r * 0.28)), fill=color, width=w)  # slot
    draw.rectangle((cx - int(r * 0.42), cy - int(r * 0.95), cx + int(r * 0.42), cy + int(r * 0.12)), outline=color, width=w)  # paper
    draw.line((cx - int(r * 0.2), cy - int(r * 0.42), cx - int(r * 0.04), cy - int(r * 0.24)), fill=color, width=w)  # tick
    draw.line((cx - int(r * 0.04), cy - int(r * 0.24), cx + int(r * 0.24), cy - int(r * 0.62)), fill=color, width=w)


def globe(draw, cx, cy, r, color):
    d.draw_brand_mark(draw, cx, cy, r, color=color)


# Category label (see card_design.CATEGORIES) -> illustration. Anything else gets the globe.
GLYPH_FOR_CATEGORY = {
    "PRESS FREEDOM": camera,
    "POLITICAL PRISONERS": bars,
    "WAR CRIMES": alert,
    "REFUGEES & MIGRATION": pin,
    "WOMEN & GIRLS": venus,
    "DIGITAL RIGHTS": eye,
    "DEMOCRACY & REPRESSION": ballot,
    "JUSTICE & ACCOUNTABILITY": scales,
}


def glyph_for(label: str):
    return GLYPH_FOR_CATEGORY.get(label, globe)
