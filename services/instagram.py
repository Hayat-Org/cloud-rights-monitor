import os
import time
import requests

INSTAGRAM_USER_ID = os.getenv("INSTAGRAM_USER_ID", "").strip()
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()
API_VERSION = "v21.0"

def post_to_instagram(caption: str, image_url: str) -> bool:
    """Publishes photos directly using Instagram API with Instagram Login (No Facebook Page)."""
    user_id = os.getenv("INSTAGRAM_USER_ID", "").strip() or INSTAGRAM_USER_ID
    access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip() or INSTAGRAM_ACCESS_TOKEN

    if not user_id or not access_token:
        print("[!] Instagram direct error: INSTAGRAM_USER_ID or INSTAGRAM_ACCESS_TOKEN missing.")
        return False

    # Step 1: Create Media Container directly on graph.instagram.com
    container_url = f"https://graph.instagram.com/{API_VERSION}/{user_id}/media"
    container_payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": access_token
    }

    try:
        res = requests.post(container_url, data=container_payload, timeout=20)
        res_data = res.json()

        if res.status_code != 200 or "id" not in res_data:
            print(f"[!] Instagram Container Creation Failed: {res.text}")
            return False

        container_id = res_data["id"]
        print(f"[+] Instagram media container created: {container_id}")

        # Step 2: Poll container status until media finishes processing
        status_url = f"https://graph.instagram.com/{API_VERSION}/{container_id}"
        is_ready = False
        for _ in range(6):
            time.sleep(3)
            check_res = requests.get(
                status_url,
                params={"fields": "status_code", "access_token": access_token},
                timeout=10
            ).json()

            status = check_res.get("status_code")
            if status == "FINISHED":
                is_ready = True
                break
            elif status == "ERROR":
                print(f"[!] Instagram container processing error: {check_res}")
                return False

        if not is_ready:
            print("[!] Instagram container processing timed out.")
            return False

        # Step 3: Publish Media Container
        publish_url = f"https://graph.instagram.com/{API_VERSION}/{user_id}/media_publish"
        publish_payload = {
            "creation_id": container_id,
            "access_token": access_token
        }

        pub_res = requests.post(publish_url, data=publish_payload, timeout=20)
        pub_data = pub_res.json()

        if pub_res.status_code == 200 and "id" in pub_data:
            print(f"[+] Successfully published to Instagram. Post ID: {pub_data['id']}")
            return True
        else:
            print(f"[!] Instagram Publish Failed: {pub_res.text}")
            return False

    except Exception as e:
        print(f"[!] Instagram Direct API exception: {e}")
        return False
