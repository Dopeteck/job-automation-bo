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

# 👉 CHANGE THESE ONCE
SUBSTACK_URL = "https://YOUR_SUBSTACK_URL"
TELEGRAM_PUBLIC_URL = "https://t.me/YOUR_TELEGRAM_CHANNEL"

# -----------------------
# PATHS
# -----------------------
LOG_FILE = Path("data/jobs_log.json")
SENT_FILE = Path("data/published_jobs.pkl")

# -----------------------
# STATE
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
        return json.loads(LOG_FILE.read_text())
    return []

# -----------------------
# TELEGRAM (UNCHANGED)
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

# -----------------------
# BLOGGER (SEO OPTIMIZED)
# -----------------------
def post_blogger(job):
    with open(TOKEN_FILE, "rb") as f:
        creds = pickle.load(f)

    service = build("blogger", "v3", credentials=creds)

    title = html.escape(job["title"])
    company = html.escape(job["company"])
    level = job["level"]
    category = html.escape(job.get("category", "Remote Jobs"))
    source = html.escape(job.get("source", "Remote"))
    desc = html.escape(job.get("short_desc", ""))

    content = f"""
<h2>{title} – Remote Job</h2>

<p>
The <b>{title}</b> position at <b>{company}</b> is a fully remote opportunity
ideal for professionals seeking <b>{level.lower()} remote jobs</b>.
This role is suitable for candidates looking for <b>work from home jobs</b>,
<b>{category.lower()} roles</b>, and flexible online careers.
</p>

<h3>Job Details</h3>
<ul>
  <li><b>Company:</b> {company}</li>
  <li><b>Experience Level:</b> {level}</li>
  <li><b>Category:</b> {category}</li>
  <li><b>Source:</b> {source}</li>
  <li><b>Location:</b> Remote / Worldwide</li>
</ul>

<h3>Job Description</h3>
<p>{desc}</p>

<p>
This position is ideal for job seekers searching for
<b>remote {category.lower()} jobs</b>,
<b>{level.lower()} work from home roles</b>,
and global career opportunities.
</p>

<h3>How to Apply</h3>
<p>
<a href="{job['link']}" target="_blank" rel="nofollow noopener">
👉 Apply directly on the company website
</a>
</p>

<hr/>

<h3>📬 Stay Updated on Remote Jobs</h3>

<p>
Never miss new <b>remote job opportunities</b>.
Subscribe below to get the latest jobs delivered instantly:
</p>

<ul>
  <li>
    📩 <b>Substack Newsletter:</b><br/>
    <a href="{SUBSTACK_URL}" target="_blank">
      Get remote jobs in your inbox
    </a>
  </li>
  <li>
    📢 <b>Telegram Channel:</b><br/>
    <a href="{TELEGRAM_PUBLIC_URL}" target="_blank">
      Join our Telegram for instant job alerts
    </a>
  </li>
</ul>

<p><i>We publish new remote jobs daily across tech, Web3, and crypto.</i></p>
"""

    service.posts().insert(
        blogId=BLOGGER_ID,
        body={
            "title": f"{job['title']} – Remote Job",
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

    jobs = sorted(jobs, key=lambda x: x.get("timestamp",""), reverse=True)

    for job in jobs:
        jid = job["id"]
        if jid in sent:
            continue

        try:
            post_telegram(job)
            post_blogger(job)
        except Exception as e:
            print(f"Publish error: {e}")
            continue

        sent.add(jid)
        save_sent(sent)

        print(f"✅ Published: {job['title']} ({job['source']})")
        break

if __name__ == "__main__":
    main()


