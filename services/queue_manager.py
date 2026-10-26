import re
from datetime import datetime, timedelta, timezone
from services.ai_engine import get_authorized_models
from services.database import supabase

def calculate_urgency_score(title: str, snippet: str) -> float:
    """Calculates news urgency score using configured AI scoring functions."""
    scorers = get_authorized_models()
    for scorer in scorers:
        try:
            score = scorer(title, snippet)
            return min(max(float(score), 1.0), 10.0)
        except Exception as e:
            print(f"[!] AI Scoring attempt failed: {e}")
            continue
    return 7.0

def process_and_queue_article(title: str, snippet: str, link: str, image_url: str, source: str) -> dict:
    """Evaluates and routes incoming RSS items, enforcing Supabase records for all tiers."""
    score = calculate_urgency_score(title, snippet)
    item_data = {
        "title": title,
        "snippet": snippet,
        "url": link,
        "image_url": image_url,
        "combined_score": score,
        "status": "pending"
    }

    # Always write to article_queue first so check_article_exists finds it
    if supabase:
        try:
            supabase.table("article_queue").upsert(item_data, on_conflict="url").execute()
        except Exception as e:
            print(f"[!] Queue upsert error: {e}")

    if score >= 8.5:
        return {"action": "fast_tracked", "data": item_data}
    elif score >= 6.8:
        return {"action": "queued", "data": item_data}
    elif score >= 5.5:
        return {"action": "low_tier_immediate", "data": item_data}
    else:
        if supabase:
            try:
                supabase.table("article_queue").update({"status": "discarded"}).eq("url", link).execute()
            except Exception:
                pass
        return {"action": "discarded", "data": item_data}

# Articles whose publish attempt failed are retried in later slots (until they expire).
PUBLISHABLE_STATUSES = ["pending", "failed_retry"]


def get_top_prioritized_queue(limit: int = 4) -> list:
    """Fetches highest-scoring publishable (pending / failed_retry) articles from Supabase."""
    if not supabase:
        return []
    try:
        res = supabase.table("article_queue") \
            .select("*") \
            .in_("status", PUBLISHABLE_STATUSES) \
            .order("combined_score", desc=True) \
            .limit(limit) \
            .execute()
        return res.data or []
    except Exception as e:
        print(f"[!] Error fetching queue: {e}")
        return []

def get_queue_status_metrics() -> tuple:
    """Returns (pending_count, next_up_title)."""
    if not supabase:
        return 0, "N/A"
    try:
        res = supabase.table("article_queue") \
            .select("title") \
            .in_("status", PUBLISHABLE_STATUSES) \
            .order("combined_score", desc=True) \
            .execute()
        data = res.data or []
        count = len(data)
        next_title = data[0]["title"] if count > 0 else "None"
        return count, next_title
    except Exception as e:
        print(f"[!] Metric fetch error: {e}")
        return 0, "N/A"

def clean_expired_queue_items() -> int:
    """Purges unpublished (pending / failed_retry) queue items older than 48 hours."""
    if not supabase:
        return 0
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        res = supabase.table("article_queue") \
            .delete() \
            .lt("created_at", cutoff) \
            .in_("status", PUBLISHABLE_STATUSES) \
            .execute()
        return len(res.data) if res.data else 0
    except Exception as e:
        print(f"[!] Expired queue cleanup error: {e}")
        return 0

def rescore_discarded_or_pending_articles(limit: int = 25) -> dict:
    """
    Re-scores recent discarded articles (e.g. when AI scoring was down and a neutral
    default was used). Anything now scoring >= 6.8 is moved back to 'pending' so the next
    publishing slot can pick it up; >= 8.5 counts as fast-tracked (highest priority).
    """
    result = {"rescored_total": 0, "newly_queued": 0, "fast_tracked": 0, "errors": []}
    if not supabase:
        return result
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        rows = supabase.table("article_queue") \
            .select("id,url,title,snippet,combined_score") \
            .eq("status", "discarded") \
            .gte("created_at", cutoff) \
            .order("created_at", desc=True) \
            .limit(limit) \
            .execute().data or []
    except Exception as e:
        result["errors"].append(f"fetch: {e}")
        return result

    for row in rows:
        try:
            score = calculate_urgency_score(row.get("title", ""), row.get("snippet", ""))
            result["rescored_total"] += 1
            update = {"combined_score": score}
            if score >= 6.8:
                update["status"] = "pending"
                result["newly_queued"] += 1
                if score >= 8.5:
                    result["fast_tracked"] += 1
            supabase.table("article_queue").update(update).eq("url", row["url"]).execute()
        except Exception as e:
            result["errors"].append(f"{str(row.get('title', ''))[:30]}: {e}")
    return result
