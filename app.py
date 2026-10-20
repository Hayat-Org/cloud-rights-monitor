import os
import time
import html
import re
import requests
import feedparser
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from config import RSS_FEEDS
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
    send_telegram_notification, send_ingestion_summary, send_publishing_summary, send_telegram_message
)
from services.threads import post_to_threads
from services.instagram import post_to_instagram, post_to_instagram_story
from services.story_generator import generate_story_canvas

# Explicit ASGI application instantiation for Uvicorn
app = FastAPI()

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
    feed_image = article_data.get("image_url") or DEFAULT_BRAND_IMAGE

    mark_article_status(article_data, "processing")

    drafts, ai_err = generate_ai_draft(title, snippet, link, recent_topics)
    if not drafts or not isinstance(drafts, dict):
        mark_article_status(article_data, "failed_retry")
        return {}

    save_article_draft(link, title, drafts.get("threads", ""), "processing")

    results = {
        "Threads": False,
        "Instagram Feed": False,
        "Instagram Story": False
    }

    # 1. Threads Direct API
    try:
        results["Threads"] = post_to_threads(
            drafts.get("threads", ""),
            feed_image if feed_image != DEFAULT_BRAND_IMAGE else None
        )
    except Exception as e:
        print(f"[!] Threads exception: {e}")

    # 2. Instagram Feed Photo
    try:
        results["Instagram Feed"] = post_to_instagram(
            drafts.get("instagram", ""),
            feed_image
        )
    except Exception as e:
        print(f"[!] Instagram Feed exception: {e}")

    # 3. Instagram Story (Branded 1080x1920 with headline & pill)
    try:
        story_image_url = generate_story_canvas(
            title=title,
            image_url=feed_image,
            category="HUMAN RIGHTS REPORT"
        )
        if story_image_url:
            results["Instagram Story"] = post_to_instagram_story(story_image_url)
    except Exception as e:
        print(f"[!] Instagram Story generation/publish exception: {e}")

    if any(results.values()):
        mark_article_status(article_data, "published")
        send_telegram_notification(drafts.get("threads", ""), title, results)
    else:
        mark_article_status(article_data, "failed_retry")

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

                real_link = resolve_google_news_url(raw_link)

                if check_article_exists(real_link, raw_title) or is_semantic_duplicate(raw_title, threshold=0.70):
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
    recent_topics = get_recent_articles(limit=15)
    batch = get_top_prioritized_queue(limit=4)
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
def health_check(): return {"status": "Online"}

@app.api_route("/media/stories/{filename}", methods=["GET", "HEAD"])
def serve_story_image(filename: str):
    """Serves generated story images to Instagram API crawler."""
    clean_filename = os.path.basename(filename)
    filepath = os.path.join("/tmp", clean_filename)
    if os.path.exists(filepath):
        return FileResponse(filepath, media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Story image not found")

@app.api_route("/ingest-feeds", methods=["GET", "HEAD"])
def trigger_ingestion(background_tasks: BackgroundTasks):
    background_tasks.add_task(ingest_feeds_task)
    return {"status": "Accepted", "task": "Ingestion & Scoring"}

@app.api_route("/publish-queue", methods=["GET", "HEAD"])
def trigger_publishing(background_tasks: BackgroundTasks):
    background_tasks.add_task(publish_queue_task)
    return {"status": "Accepted", "task": "Peak Publishing"}

@app.api_route("/rescore-queue", methods=["GET", "HEAD"])
def trigger_rescore(background_tasks: BackgroundTasks):
    background_tasks.add_task(rescore_task)
    return {"status": "Accepted", "task": "Rescore"}
