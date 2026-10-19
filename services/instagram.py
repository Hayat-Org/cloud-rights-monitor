import os
import time
import requests

INSTAGRAM_USER_ID = os.getenv("INSTAGRAM_USER_ID", "17841438996464898").strip()
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()
API_VERSION = "v21.0"

def _wait_and_publish(container_id: str, user_id: str, access_token: str) -> bool:
    """Polls container readiness and triggers final publication."""
    status_url = f"https://graph.instagram.com/{API_VERSION}/{container_id}"
    for _ in range(8):
        time.sleep(3)
        check_res = requests.get(
            status_url,
            params={"fields": "status_code", "access_token": access_token},
            timeout=10
        ).json()

        status = check_res.get("status_code")
        if status == "FINISHED":
            break
        elif status == "ERROR":
            print(f"[!] Instagram container processing failed: {check_res}")
            return False
    else:
        print("[!] Instagram container processing timed out.")
        return False

    publish_url = f"https://graph.instagram.com/{API_VERSION}/{user_id}/media_publish"
    pub_res = requests.post(
        publish_url,
        data={"creation_id": container_id, "access_token": access_token},
        timeout=20
    ).json()

    if "id" in pub_res:
        print(f"[+] Successfully published to Instagram. ID: {pub_res['id']}")
        return True

    print(f"[!] Instagram Media Publish Failed: {pub_res}")
    return False

def post_to_instagram(caption: str, image_url: str) -> bool:
    """Publishes a regular feed photo post with a caption."""
    user_id = os.getenv("INSTAGRAM_USER_ID", "").strip() or INSTAGRAM_USER_ID
    access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip() or INSTAGRAM_ACCESS_TOKEN

    if not user_id or not access_token:
        print("[!] Instagram Error: Missing credentials.")
        return False

    url = f"https://graph.instagram.com/{API_VERSION}/{user_id}/media"
    payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": access_token
    }

    try:
        res = requests.post(url, data=payload, timeout=20).json()
        if "id" not in res:
            print(f"[!] Instagram Feed Container Creation Failed: {res}")
            return False
        return _wait_and_publish(res["id"], user_id, access_token)
    except Exception as e:
        print(f"[!] Instagram Feed exception: {e}")
        return False

def post_to_instagram_story(image_url: str) -> bool:
    """Publishes a 24-hour Instagram Story (media_type=STORIES, no caption)."""
    user_id = os.getenv("INSTAGRAM_USER_ID", "").strip() or INSTAGRAM_USER_ID
    access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip() or INSTAGRAM_ACCESS_TOKEN

    if not user_id or not access_token:
        print("[!] Instagram Story Error: Missing credentials.")
        return False

    url = f"https://graph.instagram.com/{API_VERSION}/{user_id}/media"
    payload = {
        "image_url": image_url,
        "media_type": "STORIES",
        "access_token": access_token
    }

    try:
        res = requests.post(url, data=payload, timeout=20).json()
        if "id" not in res:
            print(f"[!] Instagram Story Container Creation Failed: {res}")
            return False
        return _wait_and_publish(res["id"], user_id, access_token)
    except Exception as e:
        print(f"[!] Instagram Story exception: {e}")
        return False
