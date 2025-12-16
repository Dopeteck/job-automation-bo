#!/usr/bin/env python3
"""
Unified Publisher — Telegram + Blogger
- Publishes ONE job per run
- Uses flags inside jobs_log.json
"""

import os
import json
import html
import pickle
from pathlib import Path
from telegram import Bot
from googleapiclient.discovery import build

# -----------------------
# ENV
# -----------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL   = os.getenv("TELEGRAM_CHANNEL")
BLOGGER_ID         = os.getenv("BLOGGER_ID")
TOKEN_FILE         = "token_blogger.pkl"

LOG_FILE = Path("data/jobs_log.json")

# -----------------------
# LOAD / SAVE
# -----------------------
def load_jobs():
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text())
    return []

def save_jobs(jobs):
    LOG_FILE.write_text(json.dumps(jobs, indent=2))

# -----------------------
# TELEGRAM
# -----------------------
def post_telegram(job):
    bot = Bot(TELEGRAM_BOT_TOKEN)

    msg = (
        f"🔥 <b>New Remote Job</b>\n\n"
        f"<b>{html.escape(job['title'])}</b>\n"
        f"{html.escape(job['company'])}\n"
        f"Level: {job['level']}\n\n"
        f"{html.escape(job.get('short_desc',''))}\n\n"
        f"<a href='{job['link']}'>👉 Apply here</a>"
    )

    bot.send_message(
        chat_id=TELEGRAM_CHANNEL,
        text=msg,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

# -----------------------
# BLOGGER
# -----------------------
def post_blogger(job):
    with open(TOKEN_FILE, "rb") as f:
        creds = pickle.load(f)

    service = build("blogger", "v3", credentials=creds)

    title = f"{job['title']} – Remote {job['level']} Position at {job['company']}"

    content = f"""
<h2>{html.escape(job['title'])} – Remote Job Opportunity</h2>

<p>
<strong>{html.escape(job['company'])}</strong> is hiring a
<strong>{job['level']} {html.escape(job['title'])}</strong> for a fully remote role.
</p>

<h3>Job Overview</h3>
<p>{html.escape(job.get('short_desc',''))}</p>

<h3>How to Apply</h3>
<p>
<a href="{job['link']}" target="_blank" rel="nofollow noopener">
👉 Apply for this job
</a>
</p>

<hr>
<p><em>New remote jobs posted daily.</em></p>
"""

    service.posts().insert(
        blogId=BLOGGER_ID,
        body={"title": title, "content": content},
        isDraft=False,
    ).execute()

# -----------------------
# MAIN
# -----------------------
def main():
    jobs = load_jobs()

    for job in jobs:
        if job.get("published_telegram") or job.get("published_blogger"):
            continue

        post_telegram(job)
        post_blogger(job)

        job["published_telegram"] = True
        job["published_blogger"] = True

        save_jobs(jobs)
        print(f"✅ Published: {job['title']}")
        return  # HARD STOP (one job per run)

    print("ℹ️ No unpublished jobs")

if __name__ == "__main__":
    main()
