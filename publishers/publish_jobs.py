#!/usr/bin/env python3
"""
Publisher:
- Reads logged jobs from data/jobs_log.json
- Publishes newest unseen job to Telegram & Blogger
"""

import json
import os
import pickle
import html
from pathlib import Path

from telegram import Bot
from googleapiclient.discovery import build

# -----------------------
# ENV
# -----------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL   = os.getenv("TELEGRAM_CHANNEL")
BLOGGER_ID         = os.getenv("BLOGGER_ID")

LOG_PATH = Path("data/jobs_log.json")
SENT_PATH = Path("data/published_jobs.pkl")
TOKEN_FILE = "token_blogger.pkl"

# -----------------------
# STATE
# -----------------------
def load_sent():
    if SENT_PATH.exists():
        with open(SENT_PATH, "rb") as f:
            return pickle.load(f)
    return set()

def save_sent(s):
    SENT_PATH.parent.mkdir(exist_ok=True)
    with open(SENT_PATH, "wb") as f:
        pickle.dump(s, f)

# -----------------------
# LOAD JOBS
# -----------------------
def load_jobs():
    if not LOG_PATH.exists():
        return []
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

# -----------------------
# TELEGRAM
# -----------------------
def post_telegram(job):
    bot = Bot(TELEGRAM_BOT_TOKEN)

    msg = (
        f"<b>🔥 NEW REMOTE JOB</b>\n\n"
        f"<b>{html.escape(job['title'])}</b>\n"
        f"{html.escape(job['company'])}\n"
        f"{job['level']}\n\n"
        f"<a href='{job['link']}'>👉 Apply Now</a>"
    )

    bot.send_message(
        chat_id=TELEGRAM_CHANNEL,
        text=msg,
        parse_mode="HTML"
    )

# -----------------------
# BLOGGER
# -----------------------
def post_blogger(job):
    with open(TOKEN_FILE, "rb") as f:
        creds = pickle.load(f)

    service = build("blogger", "v3", credentials=creds)

    content = f"""
<h3>{html.escape(job['title'])}</h3>
<p><b>Company:</b> {html.escape(job['company'])}</p>
<p><b>Level:</b> {job['level']}</p>
<p><a href="{job['link']}">👉 Apply Here</a></p>
"""

    service.posts().insert(
        blogId=BLOGGER_ID,
        body={
            "title": job["title"],
            "content": content
        },
        isDraft=False
    ).execute()

# -----------------------
# MAIN
# -----------------------
def main():
    jobs = load_jobs()
    sent = load_sent()

    for job in reversed(jobs):
        job_id = job["id"]
        if job_id in sent:
            continue

        post_telegram(job)
        post_blogger(job)

        sent.add(job_id)
        save_sent(sent)

        print(f"Published: {job['title']}")
        break

if __name__ == "__main__":
    main()
