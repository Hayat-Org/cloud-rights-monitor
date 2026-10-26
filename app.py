import io
import os
import time
import html
import re
import requests
import feedparser
import hmac
from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, Depends, Query
from fastapi.responses import FileResponse, Response
from config import RSS_FEEDS, CRON_SECRET, PUBLISH_BATCH_SIZE
from services.database import (
    check_article_exists, is_semantic_duplicate, save_article_draft, get_recent_articles, supabase
)
from services.ai_engine import generate_ai_draft
from services.media_extractor import extract_article_image, resolve_google_news_url
from services.queue_manager import (
    process_and_queue_article, get_top_prioritized_queue, get_queue_status_metrics,
    rescore_discarded_or_pending_articles, clean_expired_queue_items
)
from services.telegram import (
    send_telegram_notification, send_ingestion_summary, send_publishing_summary,
    send_telegram_message, send_telegram_photo, send_failure_alert, send_credential_alert
)
from services.diagnostics import pop_errors, check_credentials
from services.threads import post_to_threads
from services.instagram import post_to_instagram, post_to_instagram_story
from services.card_generator import (
    generate_feed_card, generate_story_card, render_feed_card, render_story_card
)
from services.card_design import MEDIA_DIR, source_label, outlet_from_title
from services.captions import build_threads_caption, build_instagram_caption, fallback_drafts

# Explicit ASGI application instantiation for Uvicorn
app = FastAPI()


def require_secret(x_cron_secret: str = Header(default="")):
    """Protects trigger endpoints when CRON_SECRET is configured (no-op otherwise)."""
    if CRON_SECRET and not hmac.compare_digest(x_cron_secret, CRON_SECRET):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Cron-Secret")

DEFAULT_BRAND_IMAGE = "https://images.unsplash.com/photo-1589829545856-d10d557cf95f?q=80&w=1080&auto=format&fit=crop"

def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    clean_text = re.sub(r'<[^>]+>', ' ', raw_html)
    return re.sub(r'\s+', ' ', html.unescape(clean_text)).strip()

def mark_article_status(article_data: dict, status: str):
    """Safely updates article status in Supabase by matching 'id' or 'url'."""
    if not supabase:
        return
    try:
        if "id" in article_data and article_data["id"]:
            supabase.table("article_queue").update({"status": status}).eq("id", article_data["id"]).execute()
        elif "url" in article_data and article_data["url"]:
            supabase.table("article_queue").update({"status": status}).eq("url", article_data["url"]).execute()
    except Exception as e:
        print(f"[!] Failed to update status to {status}: {e}")

def publish_single_article(article_data: dict, recent_topics: list) -> dict:
    title = article_data["title"]
    snippet = article_data["snippet"]
    link = article_data["url"]
    raw_image = article_data.get("image_url") or ""
    if raw_image == DEFAULT_BRAND_IMAGE:
        raw_image = ""  # never present the generic stock photo as if it were the story's photo
    source = source_label(link) or outlet_from_title(title)

    mark_article_status(article_data, "processing")

    drafts, ai_err = generate_ai_draft(title, snippet, link, recent_topics)
    if not drafts or not isinstance(drafts, dict):
        print(f"[!] AI drafting failed ({ai_err}); using plain fallback captions.")
        drafts = fallback_drafts(title, snippet, source)

    threads_text = build_threads_caption(drafts.get("threads", ""), link=link, source=source)
    instagram_text = build_instagram_caption(drafts.get("instagram", ""), source=source)

    save_article_draft(link, title, threads_text, "processing")

    results = {
        "Threads": False,
        "Instagram Feed": False,
        "Instagram Story": False
    }

    # Standard branded cards (same template for every post -> consistent profile grid)
    feed_card_url = generate_feed_card(title, snippet, raw_image, source)
    story_card_url = generate_story_card(title, snippet, raw_image, source)

    # 1. Threads Direct API (card image; falls back to the plain photo / text-only)
    try:
        results["Threads"] = post_to_threads(threads_text, feed_card_url or raw_image or None)
    except Exception as e:
        print(f"[!] Threads exception: {e}")

    # 2. Instagram Feed Photo (needs an image: the card, or the raw photo as a last resort)
    try:
        feed_image = feed_card_url or raw_image
        if feed_image:
            results["Instagram Feed"] = post_to_instagram(instagram_text, feed_image)
        else:
            print("[!] Instagram Feed skipped: no card and no photo available.")
    except Exception as e:
        print(f"[!] Instagram Feed exception: {e}")

    # 3. Instagram Story (branded 1080x1920 card)
    try:
        if story_card_url:
            results["Instagram Story"] = post_to_instagram_story(story_card_url)
    except Exception as e:
        print(f"[!] Instagram Story publish exception: {e}")

    errors = pop_errors()
    if any(results.values()):
        mark_article_status(article_data, "published")
        send_telegram_notification(threads_text, title, results, errors)
        if feed_card_url:
            send_telegram_photo(feed_card_url, f"Published card: {title[:120]}")
    else:
        mark_article_status(article_data, "failed_retry")
        send_failure_alert(title, errors)

    return results

def ingest_feeds_task():
    print("[*] Starting feed ingestion and scoring run...")
    recent_topics = get_recent_articles(limit=15)
    run_errors = []
    
    expired_count = clean_expired_queue_items()

    stats = {
        "feeds_scanned": len(RSS_FEEDS), "evaluated_count": 0, "purged_count": 0,
        "expired_count": expired_count, "semantic_duplicates": 0, "low_tier_count": 0,
        "low_tier_items": [], "queued_count": 0, "top_queued": [], "fast_tracked": [],
        "total_pending_queue": 0
    }

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:5]:
                raw_title = clean_html(entry.get('title', 'Unknown Title'))
                raw_link = entry.get('link', '').strip()
                snippet = clean_html(entry.get('summary', '') or entry.get('description', ''))

                if not raw_link:
                    continue

                # Cheap checks first (no network): known title / link / near-duplicate headline.
                if check_article_exists(raw_link, raw_title) or is_semantic_duplicate(raw_title, threshold=0.70):
                    print(f"[*] Article already processed/published: '{raw_title[:35]}...'")
                    continue

                # Only genuinely new items pay for the Google News -> publisher lookup.
                real_link = resolve_google_news_url(raw_link)
                if real_link != raw_link and check_article_exists(real_link, raw_title):
                    print(f"[*] Article already processed/published: '{raw_title[:35]}...'")
                    continue

                stats["evaluated_count"] += 1
                img = extract_article_image(entry, real_link)
                res = process_and_queue_article(raw_title, snippet, real_link, img, feed_url)

                if res["action"] == "discarded":
                    stats["purged_count"] += 1
                elif res["action"] == "low_tier_immediate":
                    stats["low_tier_count"] += 1
                    stats["low_tier_items"].append(res["data"])
                elif res["action"] == "queued":
                    stats["queued_count"] += 1
                    if res.get("data"): stats["top_queued"].append(res["data"])
                elif res["action"] == "fast_tracked":
                    stats["fast_tracked"].append(raw_title)
                    publish_single_article(res["data"], recent_topics)
        except Exception as e:
            run_errors.append(f"Feed error {feed_url}: {e}")

    stats["total_pending_queue"], _ = get_queue_status_metrics()
    stats["top_queued"].sort(key=lambda x: x.get("combined_score", 0), reverse=True)

    send_ingestion_summary(stats, run_errors)
    print(f"[+] Ingestion complete. Evaluated: {stats['evaluated_count']}")

    if stats["low_tier_items"]:
        print(f"[*] Processing {len(stats['low_tier_items'])} low-tier items...")
        for idx, item in enumerate(stats["low_tier_items"]):
            try:
                publish_single_article(item, recent_topics)
            except Exception as e:
                print(f"[!] Low-tier processing error: {e}")
            if idx < len(stats["low_tier_items"]) - 1:
                time.sleep(5)
        print("[+] Low-tier processing complete.")

def publish_queue_task():
    print("[*] Starting scheduled peak-window publication...")
    problems = check_credentials()
    if problems:
        print(f"[!] Credential problems: {problems}")
        send_credential_alert(problems)
    recent_topics = get_recent_articles(limit=15)
    batch = get_top_prioritized_queue(limit=PUBLISH_BATCH_SIZE)
    run_errors = []
    published_items = []

    for article in batch:
        try:
            results = publish_single_article(article, recent_topics)
            if any(results.values()):
                article["results"] = results
                published_items.append(article)
            else:
                run_errors.append(f"Failed to publish '{article['title'][:25]}'.")
            time.sleep(5)
        except Exception as e:
            run_errors.append(f"Error publishing '{article['title'][:25]}': {e}")

    remaining_count, next_up_title = get_queue_status_metrics()
    send_publishing_summary(published_items, remaining_count, next_up_title, run_errors)

def rescore_task():
    res = rescore_discarded_or_pending_articles()
    msg = (f"🔄 *RE-SCORE COMPLETE*\n\nRescored: {res['rescored_total']}\nRescued: {res['newly_queued']}\nFast-Tracked: {res['fast_tracked']}\nErrors: {len(res['errors'])}")
    send_telegram_message(msg)

@app.api_route("/", methods=["GET", "HEAD"])
def health_check():
    # RENDER_GIT_COMMIT is set by Render: shows which version is actually deployed.
    return {"status": "Online", "commit": os.getenv("RENDER_GIT_COMMIT", "")[:7]}

ALLOWED_MEDIA_KINDS = {"feed", "stories"}

@app.api_route("/media/{kind}/{filename}", methods=["GET", "HEAD"])
def serve_media(kind: str, filename: str):
    """Serves generated cards to the Instagram / Threads crawlers (public by design)."""
    if kind not in ALLOWED_MEDIA_KINDS:
        raise HTTPException(status_code=404, detail="Unknown media type")
    clean_filename = os.path.basename(filename)
    filepath = os.path.join(MEDIA_DIR, kind, clean_filename)
    if os.path.exists(filepath):
        return FileResponse(filepath, media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Image not found")

@app.get("/preview/{kind}", dependencies=[Depends(require_secret)])
def preview_card(
    kind: str,
    title: str = Query("Journalists detained as press freedom declines", max_length=300),
    snippet: str = Query("", max_length=600),
    image_url: str = Query("", max_length=1000),
    source: str = Query("Human Rights Watch", max_length=80),
):
    """Renders a card on demand so template changes can be checked without publishing.

    Disabled unless CRON_SECRET is set, because `image_url` makes the server fetch a URL.
    """
    if not CRON_SECRET:
        raise HTTPException(status_code=404, detail="Preview is disabled (set CRON_SECRET to enable)")
    if kind not in ALLOWED_MEDIA_KINDS:
        raise HTTPException(status_code=404, detail="Use /preview/feed or /preview/stories")
    renderer = render_feed_card if kind == "feed" else render_story_card
    img = renderer(title, snippet, image_url or None, source)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return Response(content=buf.getvalue(), media_type="image/jpeg")

@app.get("/diagnostics", dependencies=[Depends(require_secret)])
def diagnostics():
    """Checks Threads/Instagram tokens and account ids. Disabled unless CRON_SECRET is set."""
    if not CRON_SECRET:
        raise HTTPException(status_code=404, detail="Disabled (set CRON_SECRET to enable)")
    problems = check_credentials()
    return {"ok": not problems, "problems": problems}

@app.api_route("/ingest-feeds", methods=["GET", "HEAD"], dependencies=[Depends(require_secret)])
def trigger_ingestion(background_tasks: BackgroundTasks):
    background_tasks.add_task(ingest_feeds_task)
    return {"status": "Accepted", "task": "Ingestion & Scoring"}

@app.api_route("/publish-queue", methods=["GET", "HEAD"], dependencies=[Depends(require_secret)])
def trigger_publishing(background_tasks: BackgroundTasks):
    background_tasks.add_task(publish_queue_task)
    return {"status": "Accepted", "task": "Peak Publishing"}

@app.api_route("/rescore-queue", methods=["GET", "HEAD"], dependencies=[Depends(require_secret)])
def trigger_rescore(background_tasks: BackgroundTasks):
    background_tasks.add_task(rescore_task)
    return {"status": "Accepted", "task": "Rescore"}
