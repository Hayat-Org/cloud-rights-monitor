import time
import requests
from config import THREADS_USER_ID, THREADS_ACCESS_TOKEN
from services.diagnostics import record_error

BASE = "https://graph.threads.net/v1.0"


def _wait_until_ready(creation_id: str, headers: dict, timeout: int = 60) -> bool:
    """Polls the container until Threads says it can be published (images take a while)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data = requests.get(f"{BASE}/{creation_id}", headers=headers,
                                params={"fields": "status,error_message"}, timeout=10).json()
        except Exception as e:
            record_error("Threads", f"status check failed: {e}")
            return False
        if "error" in data:
            record_error("Threads", data["error"])
            return False
        status = data.get("status")
        if status in ("FINISHED", "PUBLISHED"):
            return True
        if status in ("ERROR", "EXPIRED"):
            record_error("Threads", f"container {status}: {data.get('error_message', '')}")
            return False
        time.sleep(3)
    record_error("Threads", f"container not ready after {timeout}s")
    return False


def _publish(text: str, image_url, headers: dict, user_id: str) -> bool:
    params = {"media_type": "IMAGE" if image_url else "TEXT", "text": text}
    if image_url:
        params["image_url"] = image_url
    res = requests.post(f"{BASE}/{user_id}/threads", headers=headers, params=params, timeout=20).json()
    if "id" not in res:
        print(f"[!] Threads Container Error: {res}")
        record_error("Threads", res.get("error", res))
        return False
    if not _wait_until_ready(res["id"], headers):
        return False
    pub = requests.post(f"{BASE}/{user_id}/threads_publish", headers=headers,
                        params={"creation_id": res["id"]}, timeout=20).json()
    if "id" in pub:
        print(f"[+] Published to Threads Post ID: {pub['id']}")
        return True
    print(f"[!] Threads Publish Error: {pub}")
    record_error("Threads", pub.get("error", pub))
    return False


def post_to_threads(caption: str, image_url: str = None) -> bool:
    """Publishes to Threads. If the image post fails, retries as a text-only post."""
    token = THREADS_ACCESS_TOKEN.strip() if THREADS_ACCESS_TOKEN else ""
    user_id = THREADS_USER_ID.strip() if THREADS_USER_ID else ""

    if not user_id or not token or not caption:
        msg = f"missing required fields: user_id={bool(user_id)}, token={bool(token)}, caption={bool(caption)}"
        print(f"[!] Threads Skipped. {msg}")
        record_error("Threads", msg)
        return False

    clean_caption = caption.strip()
    if len(clean_caption) > 490:  # API limit is 500
        clean_caption = clean_caption[:485].rstrip() + "..."

    headers = {"Authorization": f"Bearer {token}"}
    try:
        if image_url and _publish(clean_caption, image_url, headers, user_id):
            return True
        if image_url:
            print("[*] Threads image post failed; retrying as text-only.")
        return _publish(clean_caption, None, headers, user_id)
    except Exception as e:
        print(f"[!] Threads Exception: {e}")
        record_error("Threads", e)
        return False
