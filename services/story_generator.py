import os
import io
import time
import hashlib
import textwrap
import requests
from PIL import Image, ImageDraw, ImageFont

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920
DEFAULT_BRAND_IMAGE = "https://images.unsplash.com/photo-1589829545856-d10d557cf95f?q=80&w=1080&auto=format&fit=crop"
BASE_URL = os.getenv("RENDER_EXTERNAL_URL", "https://cloud-rights-monitor.onrender.com").rstrip("/")

def _get_font(size: int):
    """Loads clean sans-serif system fonts available in Linux/Render environments."""
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
    ]
    for path in font_candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()

def generate_story_canvas(
    title: str,
    image_url: str = None,
    category: str = "HUMAN RIGHTS REPORT",
    brand_name: str = "HUMAN RIGHTS AGGREGATOR",
    handle: str = "@human.rights.aggregator"
) -> str:
    """
    Renders a 1080x1920 vertical Instagram Story image with:
      - Darkened editorial background
      - Page brand title
      - Colored category pill badge
      - Bold wrapped headline
      - Instagram account handle at the bottom safe zone
    Returns the public URL to the generated image.
    """
    img_src = image_url if image_url and image_url.startswith("http") else DEFAULT_BRAND_IMAGE

    # 1. Download article image
    try:
        resp = requests.get(img_src, timeout=12)
        if resp.status_code == 200:
            bg_image = Image.open(io.BytesIO(resp.content)).convert("RGB")
        else:
            bg_image = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), color=(20, 24, 32))
    except Exception as e:
        print(f"[!] Error downloading story image from {img_src}: {e}")
        bg_image = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), color=(20, 24, 32))

    # 2. Aspect-fill & center crop to 1080x1920
    orig_w, orig_h = bg_image.size
    target_ratio = CANVAS_WIDTH / CANVAS_HEIGHT
    orig_ratio = orig_w / orig_h

    if orig_ratio > target_ratio:
        new_h = CANVAS_HEIGHT
        new_w = int(orig_w * (CANVAS_HEIGHT / orig_h))
    else:
        new_w = CANVAS_WIDTH
        new_h = int(orig_h * (CANVAS_WIDTH / orig_w))

    bg_image = bg_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - CANVAS_WIDTH) // 2
    top = (new_h - CANVAS_HEIGHT) // 2
    bg_image = bg_image.crop((left, top, left + CANVAS_WIDTH, top + CANVAS_HEIGHT))

    # 3. Apply dark editorial gradient overlay for maximum text contrast
    overlay = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)
    for y in range(CANVAS_HEIGHT):
        # Gradient opacity between 150 (60%) at top to 200 (80%) near bottom
        alpha = int(145 + (y / CANVAS_HEIGHT) * 60)
        draw_overlay.line([(0, y), (CANVAS_WIDTH, y)], fill=(10, 14, 20, alpha))

    canvas = Image.alpha_composite(bg_image.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    # 4. Fonts
    font_brand = _get_font(40)
    font_pill = _get_font(28)
    font_headline = _get_font(68)
    font_handle = _get_font(42)

    left_margin = 90

    # 5. Top Page / Brand Header (y = 260 safe zone)
    draw.text((left_margin, 260), brand_name.upper(), fill=(255, 255, 255), font=font_brand)

    # 6. Category Pill Badge (y = 335)
    pill_text = category.upper()
    bbox = draw.textbbox((0, 0), pill_text, font=font_pill)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    pill_w = text_w + 48
    pill_h = text_h + 26
    pill_x0 = left_margin
    pill_y0 = 335

    # Teal/Emerald badge (#20b2aa) matching the example
    draw.rounded_rectangle(
        [pill_x0, pill_y0, pill_x0 + pill_w, pill_y0 + pill_h],
        radius=20,
        fill=(32, 178, 140)
    )
    # Dark bold text inside pill
    draw.text((pill_x0 + 24, pill_y0 + 11), pill_text, fill=(8, 30, 24), font=font_pill)

    # 7. News Headline (wrapped, y = 490)
    lines = textwrap.wrap(title, width=22)
    start_y = 490
    line_height = 92
    for idx, line in enumerate(lines[:6]):
        draw.text(
            (left_margin, start_y + (idx * line_height)),
            line,
            fill=(255, 255, 255),
            font=font_headline
        )

    # 8. Bottom Account Handle (y = 1680 safe zone)
    draw.text((left_margin, 1680), handle, fill=(32, 178, 140), font=font_handle)

    # 9. Save generated image locally in /tmp
    file_id = hashlib.md5(f"{title}_{time.time()}".encode()).hexdigest()[:12]
    filename = f"story_{file_id}.jpg"
    filepath = os.path.join("/tmp", filename)

    canvas.save(filepath, format="JPEG", quality=92)
    print(f"[+] Generated Instagram Story canvas: {filepath} (1080x1920)")

    return f"{BASE_URL}/media/stories/{filename}"
