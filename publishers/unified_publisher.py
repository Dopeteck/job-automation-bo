#!/usr/bin/env python3
"""
Unified Publisher — Telegram + Blogger
Publishes newest unseen jobs from multiple sources,
deduplicates using job IDs from scraper.
"""

import os
import json
import pickle
import html
from pathlib import Path
from telegram import Bot
from googleapiclient.discovery import build

# -----------------------
# ENV VARIABLES
# -----------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL   = os.getenv("TELEGRAM_CHANNEL")
BLOGGER_ID         = os.getenv("BLOGGER_ID")
TOKEN_FILE         = "token_blogger.pkl"

# -----------------------
# PATHS
# -----------------------
LOG_FILE = Path("data/jobs_log.json")          # scraper output
SENT_FILE = Path("data/published_jobs.pkl")   # track published jobs

# -----------------------
# STATE HANDLING
# -----------------------
def load_sent():
    if SENT_FILE.exists():
        with open(SENT_FILE, "rb") as f:
            return pickle.load(f)
    return set()

def save_sent(sent):
    SENT_FILE.parent.mkdir(exist_ok=True)
    with open(SENT_FILE, "wb") as f:
        pickle.dump(sent, f)

def load_jobs():
    if LOG_FILE.exists():
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

# -----------------------
# JOB PUBLISHERS
# -----------------------
def post_telegram(job):
    bot = Bot(TELEGRAM_BOT_TOKEN)
    msg = (
        f"<b>🔥 NEW REMOTE JOB</b>\n\n"
        f"<b>{html.escape(job['title'])}</b>\n"
        f"{html.escape(job['company'])}\n"
        f"{job['level']}\n\n"
        f"{html.escape(job.get('short_desc',''))}\n\n"
        f"<a href='{job['link']}'>👉 Apply Now</a>"
    )
    bot.send_message(chat_id=TELEGRAM_CHANNEL, text=msg, parse_mode="HTML")

def post_blogger(job):
    with open(TOKEN_FILE, "rb") as f:
        creds = pickle.load(f)
    service = build("blogger", "v3", credentials=creds)
    content = f"""
<h3>{html.escape(job['title'])}</h3>
<p><b>Company:</b> {html.escape(job['company'])}</p>
<p><b>Level:</b> {job['level']}</p>
<p>{html.escape(job.get('short_desc',''))}</p>
<p><a href="{job['link']}">👉 Apply Here</a></p>
"""
    service.posts().insert(
        blogId=BLOGGER_ID,
        body={"title": job['title'], "content": content},
        isDraft=False
    ).execute()

# -----------------------
# MAIN LOGIC
# -----------------------
def main():
    jobs = load_jobs()
    sent = load_sent()

    # Sort newest first (optional)
    jobs = sorted(jobs, key=lambda x: x.get("timestamp",""), reverse=True)

    for job in jobs:
        jid = job["id"]
        if jid in sent:
            continue  # skip already published

        # Publish
        try:
            post_telegram(job)
            post_blogger(job)
        except Exception as e:
            print(f"Error publishing {job['title']}: {e}")
            continue

        # Mark as published
        sent.add(jid)
        save_sent(sent)

        print(f"✅ Published: {job['title']} from {job['source']}")
        break  # publish only ONE job per run

if __name__ == "__main__":
    main()

