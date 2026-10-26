"""
Backwards-compatible entry point for Story images.

The Story layout now lives in services/card_generator.py so that the feed card
and the Story share one design system (services/card_design.py).
"""
from services.card_generator import generate_story_card


def generate_story_canvas(title: str, image_url: str = None, category: str = None,
                          brand_name: str = None, handle: str = None, snippet: str = "",
                          source: str = "") -> str:
    """Returns the public URL of a 1080x1920 story card (None on failure).

    `category`, `brand_name` and `handle` are accepted for compatibility; the
    category is now detected automatically and branding comes from
    BRAND_NAME / BRAND_HANDLE environment variables.
    """
    return generate_story_card(title, snippet=snippet, image_url=image_url, source=source)
