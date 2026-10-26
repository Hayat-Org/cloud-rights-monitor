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
_threads_id_cache = {}


def resolve_threads_user_id() -> str:
    """
    The Threads account id that belongs to the configured token.

    Threads ids differ from Instagram ids and are easy to get wrong in settings, so the id
    is looked up from the token itself (once, then cached). The THREADS_USER_ID setting is
    only a fallback if that lookup fails.
    """
    token = (THREADS_ACCESS_TOKEN or "").strip()
    if not token:
        return (THREADS_USER_ID or "").strip()
    if token in _threads_id_cache:
        return _threads_id_cache[token]
    try:
        data = requests.get(
            "https://graph.threads.net/v1.0/me",
            headers={"Authorization": f"Bearer {token}"},
            params={"fields": "id"}, timeout=10,
        ).json()
        if isinstance(data, dict) and data.get("id"):
            _threads_id_cache[token] = str(data["id"])
            return _threads_id_cache[token]
    except Exception:
        pass
    return (THREADS_USER_ID or "").strip()


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
    """Problems with the Threads token (empty list = OK)."""
    if not THREADS_ACCESS_TOKEN:
        return ["Threads: no access token configured (THREADS_ACCESS_TOKEN / META_ACCESS_TOKEN)."]
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
    # The account id is taken from the token itself (resolve_threads_user_id), so a different
    # THREADS_USER_ID setting is harmless and no longer reported as a problem.
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
