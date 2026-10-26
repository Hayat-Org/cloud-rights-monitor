import os
import re
import base64
import hashlib
import requests
from config import ALLOW_AI_FALLBACK_IMAGES
from urllib.parse import quote_plus, urlparse

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5"
}

# Domains and keywords to reject for news images (logos, icons, trackers)
BLOCKED_IMAGE_DOMAINS = [
    "googleusercontent.com", "gstatic.com", "google.com", "googletagmanager",
    "favicon", "avatar", "logo-small", "default-brand", "s0-w300", "icon",
    "unsplash.com/photo-1451187580459", "analytics", "tracking", "pixel"
]

# Patterns and scripts to reject when resolving Google News publisher destination URLs
IGNORED_URL_PATTERNS = [
    "google.com", "gstatic.com", "googleusercontent.com", "schema.org", "w3.org",
    "youtube.com", "doubleclick", "google-analytics.com", "googletagmanager.com",
    "facebook.com/tr", "analytics.js", "cookiebot.com", "onetrust.com",
    "scorecardresearch.com", "adnxs.com", "criteo.com", "twitter.com/widgets"
]

# Hosts owned by Google: assets, fonts, support pages... never an article's publisher.
GOOGLE_HOST_SUFFIXES = (
    "google.com", "googleapis.com", "gstatic.com", "googleusercontent.com", "ggpht.com",
    "googleadservices.com", "googlesyndication.com", "googletagmanager.com", "youtube.com", "g.co",
)

IGNORED_URL_EXTENSIONS = (
    ".js", ".css", ".json", ".xml", ".ico", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp"
)

STATIC_FALLBACK_IMAGE = "https://images.unsplash.com/photo-1589829545856-d10d557cf95f?q=80&w=1080&auto=format&fit=crop"

def is_valid_news_image(url: str) -> bool:
    """Filters out generic placeholders, icons, and tracking pixels."""
    if not url or not url.startswith("http"):
        return False
    lower_url = url.lower()
    return not any(blocked in lower_url for blocked in BLOCKED_IMAGE_DOMAINS)

def is_valid_article_url(url: str) -> bool:
    """Filters out script assets, tracking domains, and non-article endpoints."""
    if not url or not url.startswith("http"):
        return False
    lower = url.lower()
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if any(host == suffix or host.endswith("." + suffix) for suffix in GOOGLE_HOST_SUFFIXES):
        return False
    path = parsed.path.lower()
    if any(path.endswith(ext) for ext in IGNORED_URL_EXTENSIONS):
        return False
    if any(pattern in lower for pattern in IGNORED_URL_PATTERNS):
        return False
    return True

def _decode_google_news_token(url: str) -> str:
    """
    Older Google News links (.../rss/articles/CBMi...) embed the publisher URL inside a
    base64 token, so it can be recovered without any network request. Newer tokens do not,
    in which case "" is returned.
    """
    try:
        token = urlparse(url).path.rstrip("/").split("/")[-1]
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        match = re.search(rb"https?://[\x21-\x7e]+", raw)
        if match:
            candidate = match.group(0).decode("ascii", "ignore")
            if is_valid_article_url(candidate):
                return candidate
    except Exception:
        pass
    return ""


def resolve_google_news_url(url: str) -> str:
    """
    Unwraps a Google News RSS link to the publisher URL. If the real URL cannot be
    determined it returns the ORIGINAL link (which is unique per article), never a
    guessed URL: a wrong guess shared by many articles makes the duplicate check treat
    every one of them as "already processed".
    """
    if not url or "news.google.com" not in url:
        return url

    decoded = _decode_google_news_token(url)
    if decoded:
        return decoded

    try:
        res = requests.get(url, headers=HEADERS, timeout=8, allow_redirects=True)
        # HTTP redirect already landed on the publisher
        if res.url and "news.google.com" not in res.url and is_valid_article_url(res.url):
            print(f"[+] HTTP Redirect resolved real publisher: {res.url[:50]}...")
            return res.url

        if res.status_code == 200:
            # Only accept real article-looking links (a path, not a bare domain)
            for link in re.findall(r'https?://[^\s<>"\'\\]+', res.text):
                if is_valid_article_url(link) and len(urlparse(link).path.strip("/")) > 8:
                    print(f"[+] Unwrapped Google News link to real publisher: {link[:50]}...")
                    return link
    except Exception as e:
        print(f"[!] Google News unwrap error for {url[:30]}: {e}")
    return url

def extract_image_from_html_summary(summary_html: str) -> str:
    """Scrapes embedded <img> tags from RSS HTML summaries if available."""
    if not summary_html:
        return ""
    img_matches = re.findall(r'<img\s+[^>]*?src=["\']([^"\']+)["\']', summary_html, re.IGNORECASE)
    for img_url in img_matches:
        if is_valid_news_image(img_url):
            return img_url
    return ""

def generate_ai_news_image(title: str) -> str:
    """
    Fallback ONLY: Generates a photojournalistic image via Pollinations FLUX.
    Pre-warms the image cache via HTTP GET so Meta's 5s crawler timeout does not fail.
    """
    clean_title = re.sub(r'[^a-zA-Z0-9 ]', '', title).strip()
    prompt = f"Editorial press photo for news agency report about {clean_title[:90]}. Professional photojournalism, authentic documentary style, natural lighting, candid 35mm news photograph, realistic scene, no text, no CGI, no fantasy art"
    encoded_prompt = quote_plus(prompt)
    seed = int(hashlib.md5(title.encode()).hexdigest(), 16) % 100000  # stable across restarts

    ai_image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1080&model=flux&nologo=true&seed={seed}"
    print(f"[*] Generated documentary AI fallback: {ai_image_url[:80]}...")

    # Pre-warm: Wait up to 25 seconds for Pollinations CDN to render and cache the image
    try:
        print("[*] Pre-warming AI image to prevent Meta crawler timeout (2207052)...")
        prewarm_res = requests.get(ai_image_url, headers=HEADERS, timeout=25)
        if prewarm_res.status_code == 200 and len(prewarm_res.content) > 10000:
            print("[+] AI image successfully generated, cached, and verified.")
            return ai_image_url
        else:
            print(f"[!] Pollinations returned status {prewarm_res.status_code}. Using static fallback.")
    except Exception as e:
        print(f"[!] Pollinations image pre-warming timed out or failed: {e}. Using static fallback.")

    return STATIC_FALLBACK_IMAGE

def extract_article_image(entry: dict, article_url: str) -> str:
    """Primary: Extracts authentic publisher photo from RSS or Webpage. Secondary: AI Fallback."""
    # 1. Check RSS feed media content or enclosures (Amnesty, HRW, CPJ, UN)
    if "media_content" in entry and entry["media_content"]:
        for media in entry["media_content"]:
            u = media.get("url", "")
            if is_valid_news_image(u):
                print(f"[+] Found real photo in RSS media_content: {u[:40]}...")
                return u

    if "enclosures" in entry and entry["enclosures"]:
        for enc in entry["enclosures"]:
            u = enc.get("href", "")
            if is_valid_news_image(u):
                print(f"[+] Found real photo in RSS enclosures: {u[:40]}...")
                return u

    # 2. Check embedded <img> tags in RSS summary/description
    summary_img = extract_image_from_html_summary(entry.get('summary', '') or entry.get('description', ''))
    if summary_img:
        print(f"[+] Found real photo in RSS summary HTML: {summary_img[:40]}...")
        return summary_img

    # 3. Resolve final publisher URL (unwrapping Google News links)
    real_url = resolve_google_news_url(article_url)

    # 4. Scrape OpenGraph / Twitter lead photo directly from destination webpage
    if real_url and real_url.startswith("http"):
        try:
            res = requests.get(real_url, headers=HEADERS, timeout=7, allow_redirects=True)
            if res.status_code == 200:
                html_text = res.text

                # Check meta og:image, twitter:image, or link rel="image_src"
                patterns = [
                    r'<meta\s+[^>]*?(?:property|name)=["\'](?:og:image|twitter:image)["\']\s+[^>]*?content=["\']([^"\']+)["\']',
                    r'<meta\s+[^>]*?content=["\']([^"\']+)["\']\s+[^>]*?(?:property|name)=["\'](?:og:image|twitter:image)["\']',
                    r'<link\s+[^>]*?rel=["\'](?:image_src|thumbnail)["\']\s+[^>]*?href=["\']([^"\']+)["\']'
                ]

                for pattern in patterns:
                    match = re.search(pattern, html_text, re.IGNORECASE)
                    if match:
                        img_src = match.group(1).strip()
                        if is_valid_news_image(img_src):
                            print(f"[+] Scraped real news lead photo from webpage: {img_src[:40]}...")
                            return img_src
        except Exception as e:
            print(f"[!] Webpage image scraping error for {real_url[:30]}: {e}")

    # 5. No real photo found. By default return "" so the branded typographic card is used
    #    (see services/card_generator.py). Synthetic photos are opt-in via ALLOW_AI_FALLBACK_IMAGES.
    if ALLOW_AI_FALLBACK_IMAGES:
        return generate_ai_news_image(entry.get('title', 'human rights news report'))
    return ""
