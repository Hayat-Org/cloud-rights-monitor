"""
Shared design system for every generated visual (feed cards + stories).

Keeping colours, fonts, category rules and image helpers in ONE place is what
makes the whole profile look consistent: change a token here and both the
Instagram feed card and the Story update together.
"""
import io
import os
import re
import time
import hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw, ImageFont

# --------------------------------------------------------------------------
# Brand tokens
# --------------------------------------------------------------------------
BRAND_NAME = os.getenv("BRAND_NAME", "HUMAN RIGHTS AGGREGATOR")
BRAND_HANDLE = os.getenv("BRAND_HANDLE", "@human.rights.aggregator")

NAVY = (11, 18, 32)
NAVY_SOFT = (20, 30, 50)
WHITE = (255, 255, 255)
MUTED = (160, 174, 192)
BRAND_TEAL = (32, 178, 140)

# Category -> (label, accent colour, keywords). First match with most hits wins.
CATEGORIES = [
    ("PRESS FREEDOM", (245, 158, 11),
     ["journalist", "press freedom", "censorship", "newsroom", "reporter", "broadcaster", "media outlet"]),
    ("POLITICAL PRISONERS", (239, 68, 68),
     ["political prisoner", "detained", "arrest", "imprison", "jail", "sentenced", "custody", "detention"]),
    ("WAR CRIMES", (220, 38, 38),
     ["war crime", "crimes against humanity", "airstrike", "civilian", "genocide", "atrocit", "massacre", "international criminal court"]),
    ("REFUGEES & MIGRATION", (59, 130, 246),
     ["refugee", "asylum", "migrant", "displaced", "deport"]),
    ("WOMEN & GIRLS", (236, 72, 153),
     ["women", "girls", "gender", "female", "taliban", "sexual violence"]),
    ("DIGITAL RIGHTS", (139, 92, 246),
     ["surveillance", "internet shutdown", "spyware", "digital rights", "data protection", "facial recognition"]),
    ("DEMOCRACY & REPRESSION", (168, 85, 247),
     ["election", "protest", "crackdown", "authoritarian", "repression", "opposition", "transnational"]),
    ("JUSTICE & ACCOUNTABILITY", (20, 184, 166),
     ["court", "tribunal", "justice", "accountab", "verdict", "trial"]),
]
DEFAULT_CATEGORY = ("HUMAN RIGHTS REPORT", BRAND_TEAL)

# Feed host -> short credit shown on the card
SOURCE_LABELS = {
    "hrw.org": "Human Rights Watch",
    "amnesty.org": "Amnesty International",
    "freedomhouse.org": "Freedom House",
    "un.org": "UN News",
    "ohchr.org": "UN OHCHR",
    "cpj.org": "Committee to Protect Journalists",
    "rsf.org": "Reporters Without Borders",
}

MEDIA_DIR = os.getenv("MEDIA_DIR", "/tmp/cloud-rights-media")
BASE_URL = os.getenv("RENDER_EXTERNAL_URL", "https://cloud-rights-monitor.onrender.com").rstrip("/")
MEDIA_TTL_SECONDS = 6 * 3600

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BOLD_CANDIDATES = [
    os.path.join(_REPO_ROOT, "assets", "fonts", "Bold.ttf"),  # optional: drop brand fonts here
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]
_REGULAR_CANDIDATES = [
    os.path.join(_REPO_ROOT, "assets", "fonts", "Regular.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]


def get_font(size: int, bold: bool = True):
    """Loads the first available TrueType font; drops back to Pillow's default."""
    for path in (_BOLD_CANDIDATES if bold else _REGULAR_CANDIDATES):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size)  # Pillow >= 10.1 scalable default
    except Exception:
        return ImageFont.load_default()


# --------------------------------------------------------------------------
# Content helpers
# --------------------------------------------------------------------------
def _hits(keywords: list, text: str) -> int:
    """Counts keywords present in `text`, matching at word starts (so 'law' != 'flaw')."""
    return sum(1 for k in keywords if re.search(r"\b" + re.escape(k), text))


def detect_category(title: str, snippet: str = "") -> tuple:
    """Returns (label, accent_rgb); the title counts 3x as much as the snippet."""
    title_l, snippet_l = (title or "").lower(), (snippet or "").lower()
    best, best_score = DEFAULT_CATEGORY, 0
    for label, color, keywords in CATEGORIES:
        score = 3 * _hits(keywords, title_l) + _hits(keywords, snippet_l)
        if score > best_score:
            best, best_score = (label, color), score
    return best


def source_label(url: str = "", feed_url: str = "") -> str:
    """Human-readable publisher credit; '' when unknown (e.g. Google News)."""
    for candidate in (url, feed_url):
        host = (urlparse(candidate or "").hostname or "").lower().removeprefix("www.")
        for domain, label in SOURCE_LABELS.items():
            if host == domain or host.endswith("." + domain):
                return label
    return ""


_OUTLET_SUFFIX = re.compile(r"\s+[-|–—]\s+((?:[A-Z0-9][\w.&']*)(?:\s+[A-Z0-9][\w.&']*){0,5})$")


def outlet_from_title(title: str) -> str:
    """Publisher name from a trailing ' - Outlet Name' (Google News titles); '' if none."""
    t = re.sub(r"\s+", " ", title or "").strip()
    if len(t.split()) <= 4:
        return ""
    m = _OUTLET_SUFFIX.search(t)
    return m.group(1).strip() if m else ""


def clean_headline(title: str) -> str:
    """Collapses whitespace and drops a trailing ' - Outlet Name' (Google News style).

    Only capitalised, outlet-looking suffixes are removed, so real dashes in a
    headline ("Hope - and fear") are left alone.
    """
    t = re.sub(r"\s+", " ", title or "").strip()
    t = _OUTLET_SUFFIX.sub("", t) if len(t.split()) > 4 else t
    return t or "Human rights update"


def today_label() -> str:
    return datetime.now(timezone.utc).strftime("%d %b %Y").upper()


# --------------------------------------------------------------------------
# Image helpers
# --------------------------------------------------------------------------
def download_image(url: str, timeout: int = 12):
    """Returns an RGB PIL image or None (never raises)."""
    if not url or not url.startswith("http"):
        return None
    try:
        parts = urlparse(url)
        # Some CDNs refuse hotlinked images without a Referer from the publisher's own site.
        headers = {**HTTP_HEADERS, "Referer": f"{parts.scheme}://{parts.netloc}/",
                   "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code != 200 or len(resp.content) < 2000:
            return None
        img = Image.open(io.BytesIO(resp.content))
        img.load()
        if min(img.size) < 200:  # tiny logos / thumbnails look awful when upscaled
            return None
        ratio = img.width / img.height
        if ratio > 3.0 or ratio < 0.33:  # banners / wordmarks, not a news photo
            return None
        return img.convert("RGB")
    except Exception as e:
        print(f"[!] Card image download failed ({str(url)[:60]}): {e}")
        return None


def cover_crop(img: Image.Image, width: int, height: int, focus_y: float = 0.35) -> Image.Image:
    """Aspect-fill resize + crop. focus_y biases the crop upward (faces/heads)."""
    ratio_t, ratio_o = width / height, img.width / img.height
    if ratio_o > ratio_t:
        new_h, new_w = height, int(img.width * height / img.height)
    else:
        new_w, new_h = width, int(img.height * width / img.width)
    img = img.resize((max(new_w, width), max(new_h, height)), Image.Resampling.LANCZOS)
    left = (img.width - width) // 2
    top = int((img.height - height) * focus_y)
    return img.crop((left, top, left + width, top + height))


def vertical_gradient(width: int, height: int, top_rgba: tuple, bottom_rgba: tuple) -> Image.Image:
    """RGBA vertical gradient (built from a 1px column for speed)."""
    col = Image.new("RGBA", (1, height))
    px = col.load()
    for y in range(height):
        t = y / max(height - 1, 1)
        px[0, y] = tuple(int(top_rgba[i] + (bottom_rgba[i] - top_rgba[i]) * t) for i in range(4))
    return col.resize((width, height))


LINE_SPACING = 1.22


def _wrap(draw, words: list, font, max_width: int) -> list:
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def fit_text(draw, text: str, max_width: int, max_lines: int,
             start_size: int, min_size: int, bold: bool = True,
             max_height: int = None):
    """
    Wraps `text` by pixel width and shrinks the font until it fits within
    `max_lines` AND (when given) `max_height` pixels. Truncates with an
    ellipsis only as a last resort. Returns (font, lines).
    """
    words = text.split()
    for size in range(start_size, min_size - 1, -2):
        font = get_font(size, bold)
        lines = _wrap(draw, words, font, max_width)
        fits_height = max_height is None or len(lines) * int(size * LINE_SPACING) <= max_height
        if len(lines) <= max_lines and fits_height:
            return font, lines
    font = get_font(min_size, bold)
    lines = _wrap(draw, words, font, max_width)
    allowed = max_lines
    if max_height is not None:
        allowed = min(allowed, max(1, max_height // int(min_size * LINE_SPACING)))
    lines = lines[:allowed]
    last = lines[-1]
    while last and draw.textlength(last + "…", font=font) > max_width:
        last = last[:-1]
    lines[-1] = last.rstrip() + "…"
    return font, lines


def draw_pill(draw, xy: tuple, text: str, fill: tuple, text_fill: tuple, font) -> tuple:
    """Draws a rounded label; returns its (x0, y0, x1, y1)."""
    x, y = xy
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = 26, 14
    box = (x, y, x + w + pad_x * 2, y + h + pad_y * 2)
    draw.rounded_rectangle(box, radius=(box[3] - box[1]) // 2, fill=fill)
    draw.text((x + pad_x, y + pad_y - bbox[1]), text, fill=text_fill, font=font)
    return box


def draw_brand_mark(draw, cx: int, cy: int, r: int, color: tuple = BRAND_TEAL):
    """Small original globe-with-meridians logo mark, drawn with primitives."""
    w = max(2, r // 9)
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=w)
    draw.ellipse((cx - r // 2, cy - r, cx + r // 2, cy + r), outline=color, width=w)
    draw.line((cx - r, cy, cx + r, cy), fill=color, width=w)
    draw.line((cx, cy - r, cx, cy + r), fill=color, width=w)


# --------------------------------------------------------------------------
# Output storage (served by /media/{kind}/{filename} in app.py)
# --------------------------------------------------------------------------
def cleanup_old_media(max_age: int = MEDIA_TTL_SECONDS):
    try:
        now = time.time()
        for root, _, files in os.walk(MEDIA_DIR):
            for name in files:
                path = os.path.join(root, name)
                if now - os.path.getmtime(path) > max_age:
                    os.remove(path)
    except Exception as e:
        print(f"[!] Media cleanup error: {e}")


def save_card(img: Image.Image, kind: str, seed: str) -> tuple:
    """Saves as JPEG under MEDIA_DIR/<kind>/ and returns (filepath, public_url)."""
    folder = os.path.join(MEDIA_DIR, kind)
    os.makedirs(folder, exist_ok=True)
    cleanup_old_media()
    file_id = hashlib.md5(f"{seed}_{time.time()}".encode()).hexdigest()[:12]
    filename = f"{kind}_{file_id}.jpg"
    path = os.path.join(folder, filename)
    img.save(path, format="JPEG", quality=92, optimize=True)
    return path, f"{BASE_URL}/media/{kind}/{filename}"
