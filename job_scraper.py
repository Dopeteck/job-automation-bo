#!/usr/bin/env python3
"""
job_scraper.py

One-shot job scraper & publisher:
- Run once and exit (suitable for GitHub Actions)
- Env vars:
    TELEGRAM_BOT_TOKEN   (required)
    TELEGRAM_CHANNEL     (required, e.g. @VettedWeb3jobs)
    BLOGGER_ID           (required)
    CATEGORY             (optional) one of: tech, web3, crypto
    MANUAL               set to "1" for manual run (prepopulate 9 + post one per category)
- Requires token_blogger.pkl (created via your local OAuth flow)
- Requires python-telegram-bot==13.7 (sync)
- Requires feedparser, beautifulsoup4, google-api-python-client, google-auth-oauthlib
"""

import os
import time
import pickle
import html
import re
from datetime import datetime
from bs4 import BeautifulSoup
import feedparser
import traceback

# Environment
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL")
BLOGGER_ID = os.getenv("BLOGGER_ID")
CATEGORY = os.getenv("CATEGORY")  # "tech" / "web3" / "crypto" (preferred for scheduled run)
MANUAL = os.getenv("MANUAL", "0") == "1"

SENT_STORE = "sent_jobs.pkl"
TOKEN_FILE = "token_blogger.pkl"  # must already exist (created locally)
CLIENT_SECRET_FILE = "client_secret.json"  # if your code needs it locally

# Feeds - you can expand these lists
FEEDS = {
    "tech": [
        "https://remoteok.com/remote-jobs.rss",
        "https://stackoverflow.com/jobs/feed"
    ],
    "web3": [
        "https://web3.career/rss",
        "https://thirdweb.com/careers/rss"
    ],
    "crypto": [
        "https://crypto.jobs/rss",
        "https://cryptojobslist.com/jobs.rss"
    ]
}

# Allowed HTML tags for basic formatting
ALLOWED_TAGS = ["p", "br", "b", "strong", "i", "em", "ul", "ol", "li", "a", "h1", "h2", "h3"]

# ---------------------------
# Utilities
# ---------------------------

def load_sent_jobs():
    try:
        if os.path.exists(SENT_STORE):
            with open(SENT_STORE, "rb") as f:
                return pickle.load(f)
    except Exception:
        print("Warning: failed to load sent_jobs.pkl (will recreate).")
    return set()

def save_sent_jobs(s):
    with open(SENT_STORE, "wb") as f:
        pickle.dump(s, f)

sent_jobs = load_sent_jobs()

def sanitize_html_keep_basic(html_text):
    soup = BeautifulSoup(html_text or "", "html.parser")
    for bad in soup(["script", "style"]):
        bad.decompose()
    for tag in soup.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()
        else:
            # keep only href on <a>
            if tag.name == "a":
                href = tag.get("href")
                tag.attrs = {}
                if href and isinstance(href, str) and href.startswith("http"):
                    tag.attrs["href"] = href
                else:
                    tag.unwrap()
            else:
                tag.attrs = {}
    # collapse excessive whitespace
    text = str(soup)
    text = re.sub(r'\n\s*\n', '\n', text)
    return text.strip()

def clean_text_plain(html_text, maxlen=600):
    s = BeautifulSoup(html_text or "", "html.parser").get_text(separator=" ", strip=True)
    s = re.sub(r'\s+', ' ', s)
    return s[:maxlen] + ("..." if len(s) > maxlen else "")

def detect_seniority(text):
    if not text:
        return "Not specified"
    t = text.lower()
    senior_keys = ["senior", "lead", "principal", "manager", "5+ years", "5 years"]
    mid_keys = ["mid", "intermediate", "2 years", "3 years", "4 years", "2+ years"]
    junior_keys = ["junior", "entry", "entry-level", "intern", "graduate"]
    if any(k in t for k in senior_keys):
        return "Senior"
    if any(k in t for k in mid_keys):
        return "Mid-level"
    if any(k in t for k in junior_keys):
        return "Junior"
    return "Not specified"

# ---------------------------
# Blogger (uses token_blogger.pkl)
# ---------------------------
def get_blogger_service():
    try:
        from googleapiclient.discovery import build
    except Exception as e:
        raise RuntimeError("Missing googleapiclient library. Install requirements.") from e

    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)
    else:
        raise RuntimeError(f"{TOKEN_FILE} not found. Create it locally and upload as secret for Actions.")

    service = build("blogger", "v3", credentials=creds)
    return service

def post_to_blogger(job):
    try:
        service = get_blogger_service()
        content_html = f"""
<h2>{html.escape(job.get('title',''))}</h2>
<p><b>Company:</b> {html.escape(job.get('company',''))}</p>
<p><b>Seniority:</b> {html.escape(job.get('level','Not specified'))}</p>
<hr/>
{job.get('html_description','')}
<p><b>Apply:</b> <a href="{html.escape(job.get('link',''))}">{html.escape(job.get('link',''))}</a></p>
"""
        body = {
            "kind": "blogger#post",
            "blog": {"id": BLOGGER_ID},
            "title": job.get("title","Job"),
            "content": content_html
        }
        resp = service.posts().insert(blogId=BLOGGER_ID, body=body, isDraft=False).execute()
        print("[Blogger] Posted:", job.get("title"), "->", resp.get("url"))
    except Exception as e:
        print("[Blogger] Error posting:", e)
        traceback.print_exc()

# ---------------------------
# ---------------------------
# Telegram (sync-safe, plain-text description + single clickable link)
# ---------------------------
def post_to_telegram(job):
    try:
        # use the sync v13.x library
        from telegram import Bot
        from telegram.parsemode import ParseMode
    except Exception as e:
        print("Telegram library missing or wrong version. Install python-telegram-bot==13.7")
        raise

    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    # Convert HTML/markup to plain text with line breaks
    desc_html = job.get("html_description", "") or ""
    # Use BeautifulSoup to extract text; use '\n' as separator to preserve paragraphs
    desc_text = BeautifulSoup(desc_html, "html.parser").get_text(separator="\n", strip=True)
    # Collapse multiple blank lines
    desc_text = re.sub(r'\n\s*\n+', '\n\n', desc_text).strip()

    # Truncate safely for Telegram (limit ~4096; keep smaller safety margin)
    if len(desc_text) > 3000:
        desc_text = desc_text[:3000] + "..."

    title = html.escape(job.get("title",""))
    company = html.escape(job.get("company",""))
    level = html.escape(job.get("level","Not specified"))
    apply_link = html.escape(job.get("link",""))

    # Build message: plain text body, but keep the Apply link as an HTML anchor (Telegram supports <a>)
    # We escape the text portions and then include a single <a> for the link.
    # Note: do NOT include <br> tags — use '\n' for new lines.
    body_text = (
        f"<b>🔥 NEW JOB</b>\n\n"
        f"<b>Role:</b> {title}\n"
        f"<b>Company:</b> {company}\n"
        f"<b>Seniority:</b> {level}\n\n"
        f"{html.escape(desc_text)}\n\n"
        f"<b>Apply:</b> <a href=\"{apply_link}\">Apply Here</a>"
    )

    try:
        bot.send_message(
            chat_id=TELEGRAM_CHANNEL,
            text=body_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False
        )
        print(f"[Telegram] Posted: {job.get('title')}")
    except Exception as e:
        print("[Telegram] Error posting:", e)
        # log stack for debugging
        import traceback; traceback.print_exc()


# ---------------------------
# Fetch job
# ---------------------------
def fetch_one_job_for_category(category):
    feeds = FEEDS.get(category, [])
    for feed in feeds:
        try:
            data = feedparser.parse(feed)
            if not data or not getattr(data, "entries", None):
                continue
            for entry in data.entries:
                link = getattr(entry,"link",None)
                if not link:
                    continue
                if link in sent_jobs:
                    continue
                raw_desc = getattr(entry,"summary","") or getattr(entry,"description","") or ""
                html_desc = sanitize_html_keep_basic(raw_desc)
                plain = clean_text_plain(raw_desc, maxlen=1200)
                job = {
                    "title": getattr(entry,"title","No title"),
                    "company": getattr(entry,"author","") or "",
                    "link": link,
                    "html_description": html_desc,
                    "plain_description": plain,
                    "level": detect_seniority(plain)
                }
                return job
        except Exception as e:
            print(f"[Fetch] Error fetching from {feed}: {e}")
            traceback.print_exc()
            continue
    return None

# ---------------------------
# Prepopulate (manual)
# ---------------------------
def prepopulate_first_n(n=9):
    if len(sent_jobs) > 0:
        print("[Prepopulate] Already populated. Skipping.")
        return
    print("[Prepopulate] Sending initial posts...")
    count = 0
    cats = ["tech","web3","crypto"]
    # rotate through categories
    i = 0
    while count < n and i < n * 5:
        cat = cats[i % len(cats)]
        job = fetch_one_job_for_category(cat)
        if job:
            try:
                sent_jobs.add(job["link"])
                save_sent_jobs(sent_jobs)
                post_to_blogger(job)
                post_to_telegram(job)
                count += 1
                time.sleep(1)
            except Exception as e:
                print("[Prepopulate] Error posting job:", e)
        i += 1
    print(f"[Prepopulate] Done. Sent {count} starter posts.")

# ---------------------------
# MAIN
# ---------------------------

def fallback_category_from_utc():
    """Fallback mapping if CATEGORY env not provided."""
    hour = datetime.utcnow().hour
    # map exact hours used in scheduling: 12->tech, 16->web3, 20->crypto
    if hour == 12:
        return "tech"
    if hour == 16:
        return "web3"
    if hour == 20:
        return "crypto"
    # tolerant ranges if exact hour isn't used
    if 11 <= hour <= 13:
        return "tech"
    if 15 <= hour <= 17:
        return "web3"
    if 19 <= hour <= 21:
        return "crypto"
    # default
    return "tech"

def main():
    print("job_scraper.py start - MANUAL =", MANUAL, "CATEGORY env =", CATEGORY)
    # sanity checks
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL or not BLOGGER_ID:
        print("ERROR: TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL, and BLOGGER_ID must be set in environment.")
        return

    # Manual run: prepopulate 9 starter posts and then one per category
    if MANUAL:
        try:
            prepopulate_first_n(9)
        except Exception as e:
            print("Prepopulate error:", e)
        # post one for each category immediately
        for cat in ["tech","web3","crypto"]:
            print("Manual posting for category:", cat)
            job = fetch_one_job_for_category(cat)
            if job:
                sent_jobs.add(job["link"])
                save_sent_jobs(sent_jobs)
                post_to_blogger(job)
                post_to_telegram(job)
            else:
                print("No job found for", cat)
        print("Manual run finished.")
        return

    # Automated scheduled run
    run_cat = CATEGORY or fallback_category_from_utc()
    print("Scheduled run - category:", run_cat)
    job = fetch_one_job_for_category(run_cat)
    if not job:
        print("No new", run_cat, "job found.")
        return

    sent_jobs.add(job["link"])
    save_sent_jobs(sent_jobs)

    try:
        post_to_blogger(job)
    except Exception as e:
        print("Blogger post error:", e)

    try:
        post_to_telegram(job)
    except Exception as e:
        print("Telegram post error:", e)

    print("Scheduled run finished.")

if __name__ == "__main__":
    main()
