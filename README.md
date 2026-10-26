# cloud-rights-monitor

Automated human-rights news desk. It watches 11 trusted RSS feeds, scores every item for urgency with AI,
and publishes the important ones as **branded cards** to Instagram (feed + story) and Threads, with an admin
report on Telegram.

<p>
  <img src="docs/sample-feed-card.jpg" width="320" alt="Feed card template">
  <img src="docs/sample-story-card.jpg" width="180" alt="Story card template">
</p>

## How it works

```
GitHub Actions cron ──► FastAPI on Render
                         ├─ /ingest-feeds   (every 6 h)
                         │    RSS → dedupe (URL / title / fuzzy) → image lookup → AI urgency score (Groq → Gemini)
                         │    ≥ 8.5 fast-track (publish now) · 6.8–8.4 queue · 5.5–6.7 drip · < 5.5 discard
                         └─ /publish-queue  (18:00 and 22:30 IST)
                              top N pending/failed items → AI captions → cards → Threads + IG feed + IG story → Telegram
```

| Module | Responsibility |
| --- | --- |
| `app.py` | FastAPI app, orchestration, media + preview endpoints |
| `config.py` | All environment variables and feed list |
| `services/queue_manager.py` | Scoring tiers, queue, expiry (48 h), retry of failed items, re-score |
| `services/ai_engine.py` | Urgency scoring and caption drafting (Groq with Gemini fallback) |
| `services/card_design.py` | **Design system**: colours, fonts, categories, source credits, image helpers |
| `services/card_generator.py` | **Feed card (1080×1350) and story card (1080×1920) templates** |
| `services/captions.py` | Platform limits, source credit, hashtag hygiene, AI-down fallback captions |
| `services/instagram.py`, `threads.py`, `facebook.py` | Meta Graph API clients |
| `services/media_extractor.py` | Publisher photo extraction (RSS → page `og:image`) |
| `services/database.py` | Supabase access and duplicate detection |
| `services/telegram.py` | Admin notifications |

## Card templates

Every post uses the same template so the profile grid stays consistent:

* **Photo** (publisher image, cropped) fading into a navy text panel, or a **typographic card** when no real photo exists.
* **Category pill** detected from the headline (Press Freedom, War Crimes, Political Prisoners, …) with its own accent colour.
* **Auto-fitted headline**, date, and account handle. The publisher is credited in the caption ("Source: …"), not on the image.
* **Story** variant respects Instagram's UI safe zones (top 270 px / bottom 340 px).

Tweak look and feel in `services/card_design.py` (colours, categories, source names) and layout in
`services/card_generator.py`. Optionally drop `Regular.ttf` / `Bold.ttf` into `assets/fonts/` to use brand fonts.

To preview a template without publishing (requires `CRON_SECRET`):

```
curl -H "X-Cron-Secret: $CRON_SECRET" \
  "https://<your-app>/preview/feed?title=Your+headline&source=Human+Rights+Watch" -o feed.jpg
curl -H "X-Cron-Secret: $CRON_SECRET" "https://<your-app>/preview/stories?title=Your+headline" -o story.jpg
```

### About images

Where a card's picture comes from, in order:

1. **The publisher's own lead photo** (RSS media, Open Graph / Twitter tags, or structured data on the article page; relative URLs and generic logos/placeholders are handled). The publisher is credited in the caption.
2. **A category illustration** (camera, scales of justice, prison bars, ...) on a typographic card when no real photo exists.

Synthetic "news photos" are **off by default** (`ALLOW_AI_FALLBACK_IMAGES=false`) because AI images of people can be mistaken for real documentation of real events. Stock or search-engine photos are deliberately not used either: an unrelated photo next to an abuse report can wrongly suggest it shows the event or a specific person.

## Configuration

Copy `.env.example` and set the variables on Render. Required for full operation: Supabase, at least one AI key,
Instagram/Threads tokens. Recommended: `CRON_SECRET` (also add it as a GitHub Actions **secret** with the same
name) so only the scheduler can trigger publishing. If `CRON_SECRET` is unset the endpoints stay open, as before.

The card renderer needs a TrueType font on the server; DejaVu or Liberation (present on most Linux images) work.

## Development

```
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q          # or: python -m unittest discover -s tests -t .
uvicorn app:app --reload
```

CI runs the tests on every push and pull request (`.github/workflows/ci.yml`).
