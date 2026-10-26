"""
Caption helpers: guarantee every post carries source credit, fits platform
limits, and still has sensible text when every AI provider is down.
"""
import re
from services.card_design import clean_headline

THREADS_LIMIT = 490          # API hard limit is 500 characters
INSTAGRAM_LIMIT = 2200       # caption hard limit
MAX_HASHTAGS = 8
MAX_LINK_CHARS = 100         # longer links (e.g. Google News tokens) would crowd out the text
DEFAULT_HASHTAGS = ["#HumanRights", "#Justice", "#PressFreedom", "#GlobalNews"]


def _trim(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def fallback_drafts(title: str, snippet: str, source: str = "") -> dict:
    """Plain, factual captions used only when all AI engines fail."""
    title = clean_headline(title)
    body = (snippet or "").strip()
    body = _trim(body, 220) if body else ""
    threads = f"{title}\n\n{body}".strip()
    instagram = f"{title}\n\n{body}".strip()
    return {
        "threads": _trim(threads, 380),
        "instagram": f"{instagram}\n\n{' '.join(DEFAULT_HASHTAGS)}",
    }


def normalize_hashtags(caption: str) -> tuple:
    """Splits a caption into (body_without_hashtags, unique_capped_hashtags)."""
    tags = re.findall(r"#\w+", caption or "")
    body = re.sub(r"#\w+", "", caption or "")
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    seen, unique = set(), []
    for t in tags:
        if t.lower() not in seen:
            seen.add(t.lower())
            unique.append(t)
    return body, unique[:MAX_HASHTAGS]


def build_threads_caption(text: str, link: str = "", source: str = "") -> str:
    """Threads post: body + credit + link, always within the platform limit."""
    text = re.sub(r"#\w+", "", text or "").strip()  # house rule: no hashtags on Threads
    tail_parts = []
    if source:
        tail_parts.append(f"Source: {source}")
    if link and len(link) <= MAX_LINK_CHARS:
        tail_parts.append(link)
    tail = "\n\n" + "\n".join(tail_parts) if tail_parts else ""
    room = THREADS_LIMIT - len(tail)
    return _trim(text, max(room, 80)) + tail


def build_instagram_caption(text: str, source: str = "") -> str:
    """Instagram caption: body, credit line, then one clean hashtag line."""
    body, tags = normalize_hashtags(text)
    if not tags:
        tags = DEFAULT_HASHTAGS
    credit = f"\n\nSource: {source}" if source else ""
    tag_line = "\n\n" + " ".join(tags)
    room = INSTAGRAM_LIMIT - len(credit) - len(tag_line)
    return _trim(body, room) + credit + tag_line
