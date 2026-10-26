"""
Standard branded templates for the profile.

  * feed card  - 1080x1350 (Instagram 4:5 portrait, also used on Threads)
  * story card - 1080x1920 (9:16) with Instagram UI safe-zones respected

Both templates share the same visual language (see card_design.py):
photo on top / full-bleed, category pill in the category accent colour,
auto-fitted headline, publisher credit, date and account handle.
When there is no usable photo, a typographic card is rendered instead of a
random stock/AI picture, so the grid always stays on-brand and honest.
"""
from PIL import Image, ImageDraw, ImageFilter

from services import card_design as d

FEED_SIZE = (1080, 1350)
STORY_SIZE = (1080, 1920)

# Instagram covers roughly the top 250px and bottom 340px of a story with UI.
STORY_SAFE_TOP = 270
STORY_SAFE_BOTTOM = 1580
MARGIN = 72


def _typographic_backdrop(width: int, height: int, accent: tuple) -> Image.Image:
    """Photo-less background: navy gradient, accent glow and a large watermark mark."""
    bg = d.vertical_gradient(width, height, d.NAVY_SOFT + (255,), d.NAVY + (255,))
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((width * 0.35, -height * 0.15, width * 1.25, height * 0.55), fill=accent + (60,))
    glow = glow.filter(ImageFilter.GaussianBlur(max(width // 8, 40)))
    bg = Image.alpha_composite(bg, glow)
    mark = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d.draw_brand_mark(ImageDraw.Draw(mark), int(width * 0.72), int(height * 0.30), int(width * 0.32),
                      color=accent + (30,))
    return Image.alpha_composite(bg, mark)


def _photo_backdrop(photo: Image.Image, width: int, height: int) -> Image.Image:
    return d.cover_crop(photo, width, height).convert("RGBA")


def _brand_header(draw, x: int, y: int, right_edge: int, date_text: str):
    d.draw_brand_mark(draw, x + 22, y + 22, 22)
    draw.text((x + 62, y + 2), d.BRAND_NAME, fill=d.WHITE, font=d.get_font(26))
    f_date = d.get_font(24, bold=False)
    w = draw.textlength(date_text, font=f_date)
    draw.text((right_edge - w, y + 6), date_text, fill=d.MUTED, font=f_date)


def render_feed_card(title: str, snippet: str = "", image_url: str = None,
                     source: str = "", category: tuple = None) -> Image.Image:
    """Returns the finished 1080x1350 feed card as a PIL image.

    `source` is accepted for compatibility but is NOT drawn on the card: the publisher
    is credited in the caption instead.
    """
    w, h = FEED_SIZE
    headline = d.clean_headline(title)
    label, accent = category or d.detect_category(headline, snippet)

    photo = d.download_image(image_url)
    photo_h = 790

    canvas = Image.new("RGBA", (w, h), d.NAVY + (255,))
    if photo:
        canvas.paste(_photo_backdrop(photo, w, photo_h), (0, 0))
        # darken top for header legibility, fade the bottom into the text panel
        canvas = Image.alpha_composite(canvas, _paste_layer(
            d.vertical_gradient(w, 220, d.NAVY + (200,), d.NAVY + (0,)), (0, 0), (w, h)))
        canvas = Image.alpha_composite(canvas, _paste_layer(
            d.vertical_gradient(w, 360, d.NAVY + (0,), d.NAVY + (255,)), (0, photo_h - 360), (w, h)))
    else:
        canvas.paste(_typographic_backdrop(w, h, accent), (0, 0))

    draw = ImageDraw.Draw(canvas)
    _brand_header(draw, MARGIN, 56, w - MARGIN, d.today_label())

    # --- text panel -------------------------------------------------------
    pill_y = 800 if photo else 520
    d.draw_pill(draw, (MARGIN, pill_y), label, accent, d.NAVY, d.get_font(26))

    footer_y = h - 112
    divider_y = footer_y - 30
    y = pill_y + 92
    font, lines = d.fit_text(draw, headline, w - MARGIN * 2, 6, 66 if photo else 84, 38,
                             max_height=divider_y - 24 - y)
    line_h = int(font.size * d.LINE_SPACING)
    for line in lines:
        draw.text((MARGIN, y), line, fill=d.WHITE, font=font)
        y += line_h

    # --- footer -----------------------------------------------------------
    draw.line((MARGIN, divider_y, w - MARGIN, divider_y), fill=(48, 60, 84), width=2)
    f_handle = d.get_font(30)
    draw.text((MARGIN, footer_y - 2), d.BRAND_HANDLE, fill=accent, font=f_handle)
    draw.rectangle((0, h - 14, w, h), fill=accent)

    return canvas.convert("RGB")


def render_story_card(title: str, snippet: str = "", image_url: str = None,
                      source: str = "", category: tuple = None) -> Image.Image:
    """Returns the finished 1080x1920 story card as a PIL image.

    `source` is accepted for compatibility but is NOT drawn on the card: the publisher
    is credited in the caption instead.
    """
    w, h = STORY_SIZE
    headline = d.clean_headline(title)
    label, accent = category or d.detect_category(headline, snippet)

    photo = d.download_image(image_url)
    if photo:
        canvas = _photo_backdrop(photo, w, h)
        canvas = Image.alpha_composite(canvas, d.vertical_gradient(w, h, d.NAVY + (120,), d.NAVY + (140,)))
        canvas = Image.alpha_composite(canvas, _paste_layer(
            d.vertical_gradient(w, 900, d.NAVY + (0,), d.NAVY + (245,)), (0, h - 900), (w, h)))
    else:
        canvas = _typographic_backdrop(w, h, accent)

    draw = ImageDraw.Draw(canvas)
    _brand_header(draw, MARGIN, STORY_SAFE_TOP, w - MARGIN, d.today_label())

    # Build the lower block bottom-up so it always ends at the safe line.
    f_handle = d.get_font(36)
    f_cta = d.get_font(28, bold=False)
    footer_y = STORY_SAFE_BOTTOM - 110
    draw.rectangle((MARGIN, footer_y - 40, MARGIN + 120, footer_y - 34), fill=accent)
    draw.text((MARGIN, footer_y), d.BRAND_HANDLE, fill=accent, font=f_handle)
    draw.text((MARGIN, footer_y + 54), "Full report in our latest post", fill=d.MUTED, font=f_cta)

    headline_bottom = footer_y - 90
    font, lines = d.fit_text(draw, headline, w - MARGIN * 2, 8, 80, 46, max_height=760)
    line_h = int(font.size * d.LINE_SPACING)
    block_h = line_h * len(lines)
    y = headline_bottom - block_h
    pill_y = y - 110
    d.draw_pill(draw, (MARGIN, pill_y), label, accent, d.NAVY, d.get_font(30))
    for line in lines:
        draw.text((MARGIN, y), line, fill=d.WHITE, font=font)
        y += line_h

    return canvas.convert("RGB")


def _paste_layer(layer: Image.Image, pos: tuple, size: tuple) -> Image.Image:
    """Places `layer` on a transparent RGBA canvas of `size` at `pos`."""
    base = Image.new("RGBA", size, (0, 0, 0, 0))
    base.paste(layer, pos)
    return base


# --------------------------------------------------------------------------
# Public helpers used by app.py (return public URL, or None on failure)
# --------------------------------------------------------------------------
def generate_feed_card(title: str, snippet: str = "", image_url: str = None, source: str = "") -> str:
    try:
        img = render_feed_card(title, snippet, image_url, source)
        path, url = d.save_card(img, "feed", title)
        print(f"[+] Generated feed card: {path} {img.size}")
        return url
    except Exception as e:
        print(f"[!] Feed card generation failed: {e}")
        return None


def generate_story_card(title: str, snippet: str = "", image_url: str = None, source: str = "") -> str:
    try:
        img = render_story_card(title, snippet, image_url, source)
        path, url = d.save_card(img, "stories", title)
        print(f"[+] Generated story card: {path} {img.size}")
        return url
    except Exception as e:
        print(f"[!] Story card generation failed: {e}")
        return None
