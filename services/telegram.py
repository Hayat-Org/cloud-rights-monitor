import re
import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def escape_md(text: str) -> str:
    """Escapes legacy-Markdown control characters so headlines can't break the message."""
    return re.sub(r"([_*`\[])", r"\\\1", text or "")


def send_telegram_photo(image_url: str, caption: str = "") -> bool:
    """Sends the generated card to the admin chat for a quick visual check."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not image_url:
        return False
    try:
        res = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
            json={"chat_id": TELEGRAM_CHAT_ID, "photo": image_url, "caption": caption[:1000]},
            timeout=15,
        )
        return res.status_code == 200
    except Exception as e:
        print(f"[!] Telegram photo error: {e}")
        return False

def send_telegram_message(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload, timeout=8)
        if res.status_code == 400:  # usually "can't parse entities": resend as plain text
            payload.pop("parse_mode")
            res = requests.post(url, json=payload, timeout=8)
        return res.status_code == 200
    except Exception as e:
        print(f"[!] Telegram send error: {e}")
        return False

def send_telegram_notification(draft_text: str, title: str, results: dict, errors: dict = None):
    threads_status = "✅" if results.get("Threads") else "❌"
    ig_feed_status = "✅" if results.get("Instagram Feed") else "❌"
    ig_story_status = "✅" if results.get("Instagram Story") else "❌"

    msg = (
        f"📣 *AUTO-PUBLISH SUMMARY*\n\n"
        f"📌 *Headline:* {escape_md(title[:120])}\n\n"
        f"📊 *Platform Status:*\n"
        f"{threads_status} Threads\n"
        f"{ig_feed_status} Instagram Feed\n"
        f"{ig_story_status} Instagram Story\n\n"
        f"📝 *Draft Overview:*\n{escape_md(draft_text[:300])}..."
    )
    if errors:
        msg += "\n\n⚠️ *Errors:*\n" + "\n".join(f"• {k}: {escape_md(v[:160])}" for k, v in errors.items())
    send_telegram_message(msg)


def send_failure_alert(title: str, errors: dict):
    """Sent when an article could not be published ANYWHERE (previously silent)."""
    detail = "\n".join(f"• {k}: {escape_md(v[:200])}" for k, v in errors.items()) or "• No error details captured."
    send_telegram_message(f"❌ *PUBLISH FAILED*\n\n📌 {escape_md(title[:120])}\n\n{detail}")


def send_credential_alert(problems: list):
    send_telegram_message("🔑 *CREDENTIAL CHECK FAILED*\n\n" + "\n".join(f"• {escape_md(p)}" for p in problems))

def send_ingestion_summary(stats: dict, run_errors: list):
    err_text = "\n".join(run_errors) if run_errors else "No errors. All systems optimal."
    msg = (
        f"📊 *FEED INGESTION & QUEUE REPORT*\n\n"
        f"🔹 *Summary (4-Tier Routing):*\n"
        f"• Evaluated: {stats.get('evaluated_count', 0)}\n"
        f"• Purged (<5.5): {stats.get('purged_count', 0)}\n"
        f"• Expired (>48h): {stats.get('expired_count', 0)}\n"
        f"• Low-Tier Drip (5.5-6.7): {stats.get('low_tier_count', 0)}\n"
        f"• Prime Queued (6.8-8.4): {stats.get('queued_count', 0)}\n"
        f"• Fast-Tracked (>=8.5): {len(stats.get('fast_tracked', []))}\n\n"
        f"📦 *Queue Status:*\n"
        f"• Total Pending Prime Articles: {stats.get('total_pending_queue', 0)}\n\n"
        f"⚠️ *Diagnostics Log:*\n`{err_text}`"
    )
    send_telegram_message(msg)

def send_publishing_summary(published_items: list, remaining_count: int, next_up_title: str, run_errors: list):
    pub_count = len(published_items)
    err_text = "\n".join(run_errors) if run_errors else "No errors reported."
    msg = (
        f"🚀 *PEAK PUBLISHING SLOT COMPLETE*\n\n"
        f"✅ *Articles Published ({pub_count}):*\n"
        f"• Total processed in window: {pub_count}\n\n"
        f"📦 *Queue Status Remaining:*\n"
        f"• Items Still in Queue: {remaining_count}\n"
        f"• Next Up: {escape_md(next_up_title[:50])}\n\n"
        f"⚠️ *Diagnostics Log:*\n`{err_text}`"
    )
    send_telegram_message(msg)
