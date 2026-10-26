"""
Failure visibility: remembers the last API error per platform and verifies that
the configured tokens / account IDs actually work, so problems show up on
Telegram instead of silently as "nothing was posted".
"""
import requests

from config import (
    THREADS_USER_ID, THREADS_ACCESS_TOKEN, IG_USER_ID, INSTAGRAM_ACCESS_TOKEN,
)

_errors = {}


def record_error(platform: str, detail) -> None:
    """Stores a short, token-free description of the last failure for `platform`."""
    text = str(detail)
    for secret in (THREADS_ACCESS_TOKEN, INSTAGRAM_ACCESS_TOKEN):
        if secret:
            text = text.replace(secret, "***")
    _errors[platform] = text[:300]


def pop_errors() -> dict:
    """Returns and clears the recorded errors."""
    out = dict(_errors)
    _errors.clear()
    return out


def _api_error(data) -> str:
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        return f"{err.get('type', 'Error')} {err.get('code', '')}: {err.get('message', '')}".strip()
    return ""


def check_threads() -> list:
    """Problems with the Threads token / user id (empty list = OK)."""
    if not THREADS_ACCESS_TOKEN:
        return ["Threads: no access token configured (THREADS_ACCESS_TOKEN / META_ACCESS_TOKEN)."]
    if not THREADS_USER_ID:
        return ["Threads: no user id configured (THREADS_USER_ID)."]
    try:
        res = requests.get(
            "https://graph.threads.net/v1.0/me",
            headers={"Authorization": f"Bearer {THREADS_ACCESS_TOKEN}"},
            params={"fields": "id,username"}, timeout=10,
        )
        data = res.json()
    except Exception as e:
        return [f"Threads: could not reach the API ({e})."]
    msg = _api_error(data)
    if msg:
        return [f"Threads token rejected - {msg}. Generate a new Threads token (they expire after ~60 days)."]
    if str(data.get("id")) != str(THREADS_USER_ID):
        return [f"Threads: THREADS_USER_ID ({THREADS_USER_ID}) does not match the token's account "
                f"(@{data.get('username')}, id {data.get('id')}). Threads ids differ from Instagram ids."]
    return []


def check_instagram() -> list:
    """Problems with the Instagram token (empty list = OK)."""
    if not INSTAGRAM_ACCESS_TOKEN:
        return ["Instagram: no access token configured (INSTAGRAM_ACCESS_TOKEN / META_ACCESS_TOKEN)."]
    try:
        res = requests.get(
            "https://graph.instagram.com/v21.0/me",
            params={"fields": "user_id,username", "access_token": INSTAGRAM_ACCESS_TOKEN}, timeout=10,
        )
        data = res.json()
    except Exception as e:
        return [f"Instagram: could not reach the API ({e})."]
    msg = _api_error(data)
    if msg:
        return [f"Instagram token rejected - {msg}. Refresh the long-lived token (expires after ~60 days)."]
    return []


def check_credentials() -> list:
    return check_threads() + check_instagram()
