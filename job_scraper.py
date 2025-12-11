"""
master_job_bot.py
Master automation:
- Fetch jobs from RSS / JSON sources
- Detect seniority
- Post full formatted job (safe HTML) to Blogger
- Post formatted job (HTML) to Telegram
- Scheduled posting at 12:00/16:00/20:00 UTC
- Prepopulate first 9 posts
- Persist sent job IDs to disk
"""

import os
import time
import pickle
import html
import re
from datetime import datetime
from bs4 import BeautifulSoup
import feedparser
import schedule
import requests
import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL = os.getenv("TELEGRAM_CHANNEL")
BLOGGER_ID = os.getenv("BLOGGER_ID")


# Telegram
from telegram import Bot
from telegram.constants import ParseMode


# Blogger (Google API)
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow

# ---------------------------
# CONFIG (use env vars if available)
# ---------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or "PUT_YOUR_TOKEN_HERE"
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL") or "@VettedWeb3jobs"
BLOG_ID = os.getenv("BLOG_ID") or "152513194211999512"
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET") or "client_secret.json"

# Posting schedule (UTC)
SCHEDULES = {
    "tech": "12:00",   # Tech job at 12:00 UTC
    "web3": "16:00",   # Web3 job at 16:00 UTC
    "crypto": "20:00"  # Crypto job at 20:00 UTC
}

# Feeds
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
        "https://cryptojobslist.com/jobs.rss"   # if this fails, it will be skipped
    ]
}

# Persistence file for sent jobs
SENT_STORE = "sent_jobs.pkl"

# Blogger API scope
SCOPES = ["https://www.googleapis.com/auth/blogger"]

# ---------------------------
# HELPERS
# ---------------------------

def load_sent_jobs():
    if os.path.exists(SENT_STORE):
        with open(SENT_STORE, "rb") as f:
            return pickle.load(f)
    return set()

def save_sent_jobs(s):
    with open(SENT_STORE, "wb") as f:
        pickle.dump(s, f)

sent_jobs = load_sent_jobs()

# sanitize HTML: allow only safe tags, keep basic formatting for blog+telegram
ALLOWED_TAGS = ["p", "br", "b", "strong", "i", "em", "ul", "ol", "li", "a", "h1", "h2", "h3", "h4"]

def sanitize_html_keep_basic(html_text):
    """Return safe HTML string keeping only allowed tags and safe hrefs."""
    soup = BeautifulSoup(html_text or "", "html.parser")

    # Remove scripts, styles, comments
    for bad in soup(["script", "style"]):
        bad.decompose()

    # Strip attributes except href on <a>
    for tag in soup.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()  # remove tag but keep inner text
        else:
            # keep only href on <a>, remove other attrs
            if tag.name == "a":
                href = tag.get("href")
                tag.attrs = {}
                if href and href.startswith("http"):
                    tag.attrs["href"] = href
                else:
                    # convert to plain text if non-http href
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

# seniority detection (keyword-based)
def detect_seniority(text):
    if not text:
        return "Not specified"
    t = text.lower()
    senior_keys = ["senior", "lead", "principal", "manager", "5+ years", "5 years", "seniority"]
    mid_keys = ["mid", "intermediate", "2 years", "3 years", "4 years", "2+ years"]
    junior_keys = ["junior", "entry", "entry-level", "0-1", "graduate", "trainee", "intern"]

    if any(k in t for k in senior_keys):
        return "Senior"
    if any(k in t for k in mid_keys):
        return "Mid-level"
    if any(k in t for k in junior_keys):
        return "Junior"
    return "Not specified"

# Blogger auth: Desktop flow (first-run will open browser)
def get_blogger_service():
    creds = None
    token_file = "token_blogger.pkl"
    if os.path.exists(token_file):
        with open(token_file, "rb") as f:
            creds = pickle.load(f)
    if not creds:
        flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_CLIENT_SECRET, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(token_file, "wb") as f:
            pickle.dump(creds, f)
    service = build("blogger", "v3", credentials=creds)
    return service

# Post to Blogger
def post_to_blogger(job):
    try:
        service = get_blogger_service()
        content_html = f"""
<h2>{html.escape(job['title'])}</h2>
<p><b>Company:</b> {html.escape(job.get('company',''))}</p>
<p><b>Seniority:</b> {html.escape(job.get('level','Not specified'))}</p>
<hr/>
{job.get('html_description','')}
<p><b>Apply:</b> <a href="{html.escape(job['link'])}">{html.escape(job['link'])}</a></p>
"""
        body = {
            "kind": "blogger#post",
            "blog": {"id": BLOG_ID},
            "title": job['title'],
            "content": content_html
        }
        service.posts().insert(blogId=BLOG_ID, body=body, isDraft=False).execute()
        print(f"[Blogger] Posted: {job['title']}")
    except Exception as e:
        print("[Blogger] Error posting:", e)

# Telegram send: send sanitized HTML (Telegram supports a subset)
bot = Bot(token=TELEGRAM_BOT_TOKEN)

def post_to_telegram(job):
    try:
        # Compose message using Telegram's HTML parse mode
        description_html = job.get('html_description', '')
        # Telegram supports <b>, <i>, <a>, <code>, <pre>, <br>, <strong>, <em>, <u>
        # We'll keep a small subset: p -> <br>, b/strong, i/em, a
        # sanitize and convert <p> to <br>
        safe = sanitize_html_keep_basic(description_html)
        # Convert block tags to newlines for Telegram where necessary
        safe = safe.replace("</p>", "<br>").replace("<p>", "")
        # Shorten if too long for Telegram message if needed:
        if len(safe) > 2800:
            safe = safe[:2800] + "..."

        msg = f"<b>🔥 NEW JOB</b>\n\n<b>Role:</b> {html.escape(job['title'])}\n<b>Company:</b> {html.escape(job.get('company',''))}\n<b>Seniority:</b> {html.escape(job.get('level','Not specified'))}\n\n{safe}\n\n<b>Apply:</b> <a href=\"{html.escape(job['link'])}\">{html.escape(job['link'])}</a>"
        bot.send_message(chat_id=TELEGRAM_CHANNEL, text=msg, parse_mode=ParseMode.HTML, disable_web_page_preview=False)
        print(f"[Telegram] Posted: {job['title']}")
    except Exception as e:
        print("[Telegram] Error posting:", e)

# ---------------------------
# Fetching jobs: get first unseen job per category
# ---------------------------

def fetch_one_job_for_category(category):
    feeds = FEEDS.get(category, [])
    for feed in feeds:
        try:
            data = feedparser.parse(feed)
            if not data or not getattr(data, "entries", None):
                continue
            for entry in data.entries:
                link = getattr(entry, "link", None)
                if not link:
                    continue
                job_id = link
                if job_id in sent_jobs:
                    continue
                # build job dict
                raw_desc = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
                html_desc = sanitize_html_keep_basic(raw_desc)
                plain = clean_text_plain(raw_desc, maxlen=1200)
                job = {
                    "title": getattr(entry, "title", "No title"),
                    "company": getattr(entry, "author", "") or getattr(entry, "company", "") or "",
                    "link": link,
                    "html_description": html_desc,
                    "plain_description": plain
                }
                job['level'] = detect_seniority(job['plain_description'])
                return job
        except Exception as e:
            print(f"[Fetch] Error fetching from {feed}: {e}")
            continue
    return None

# ---------------------------
# Posting functions invoked by schedule
# ---------------------------

def post_for_category(category):
    job = fetch_one_job_for_category(category)
    if not job:
        print(f"[Schedule] No new {category} job found at {datetime.utcnow().isoformat()} UTC")
        return

    # Mark as sent BEFORE posting to avoid re-post on failure loops
    sent_jobs.add(job['link'])
    save_sent_jobs(sent_jobs)

    # Post to Blogger then Telegram
    post_to_blogger(job)
    post_to_telegram(job)

# Prepopulate: send 9 initial items (3 per category if available)
def prepopulate_first_n(n=9):
    if len(sent_jobs) > 0:
        print("[Prepopulate] Already populated (sent_jobs not empty). Skipping prepopulate.")
        return
    print("[Prepopulate] Sending initial posts...")
    count = 0
    cats = list(FEEDS.keys())
    i = 0
    while count < n and i < n*3:
        cat = cats[i % len(cats)]
        job = fetch_one_job_for_category(cat)
        if job:
            sent_jobs.add(job['link'])
            save_sent_jobs(sent_jobs)
            post_to_blogger(job)
            post_to_telegram(job)
            count += 1
            time.sleep(2)
        i += 1
    print(f"[Prepopulate] Done. Sent {count} starter posts.")

# ---------------------------
# Setup schedule
# ---------------------------

def setup_schedule():
    for cat, hhmm in SCHEDULES.items():
        schedule.every().day.at(hhmm).do(post_for_category, category=cat)
        print(f"[Scheduler] {cat} scheduled at {hhmm} UTC")

# ---------------------------
# MAIN
# ---------------------------

if __name__ == "__main__":
    print("Starting master job bot...")
    # prepopulate if empty
    prepopulate_first_n(9)
    # set up daily schedule
    setup_schedule()
    # run loop
    while True:
        schedule.run_pending()
        time.sleep(5)
