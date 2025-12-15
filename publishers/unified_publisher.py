#!/usr/bin/env python3
"""
Unified Publisher — Telegram + Blogger
Publishes ONE unseen job per run.
State is stored ONLY in jobs_log.json (no pickle files).
"""

import os
import json
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

# CHANGE THESE
SUBSTACK_URL = "https://YOUR_SUBSTACK_URL"
TELEGRAM_PUBLIC_URL = "https://t.me/YOUR_TELEGRAM_CHANNEL"

# -----------------------
# PATH
# -----------------------
LOG_FILE = Path("data/jobs_log.json")

# -----------------------
# LOAD / SAVE JOBS
# -----------------------
def load_jobs():
    if LOG_FILE.exists():
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_jobs(jobs):
    LOG_FILE.write_text(json.dumps(jobs, indent=2))

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
        f"{html.escape(job.get('short_desc',''))}\n\n"
        f"<a href='{job['link']}'>👉 Apply Now</a>"
    )

    bot.send_message(
        chat_id=TELEGRAM_CHANNEL,
        text=msg,
        parse_mode="HTML"
    )

# -----------------------
# BLOGGER (SEO OPTIMISED)
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
<h2>{title} – Remote Job Opportunity</h2>

<p>
The <b>{title}</b> position at <b>{company}</b> is a fully remote role
designed for professionals seeking <b>{level.lower()} remote jobs</b>.
This opportunity is ideal for candidates searching for
<b>work from home jobs</b>, <b>{category.lower()} roles</b>,
and location-independent careers.
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
This role is suitable for professionals looking for
<b>remote {category.lower()} jobs</b>,
<b>{level.lower()} work-from-home positions</b>,
and global online opportunities.
</p>

<h3>How to Apply</h3>
<p>
<a href="{job['link']}" target="_blank" rel="nofollow noopener">
👉 Apply directly on the company website
</a>
</p>

<hr/>

<h3>📬 Stay Updated on Remote Jobs</h3>
<ul>
  <li>
    📩 <b>Substack Newsletter</b><br/>
    <a href="{SUBSTACK_URL}" target="_blank">
      Get curated remote jobs delivered to your inbox
    </a>
  </li>
  <li>
    📢 <b>Telegram Channel</b><br/>
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
# MAIN (ONE JOB ONLY)
# -----------------------
def main():
    jobs = load_jobs()

    # newest first
    jobs = sorted(jobs, key=lambda x: x.get("timestamp", ""), reverse=True)

    for job in jobs:
        if job.get("published"):
            continue

        # publish exactly ONE job
        post_telegram(job)
        post_blogger(job)

        # mark as published IN jobs_log.json
        job["published"] = True
        save_jobs(jobs)

        print(f"✅ Published ONE job: {job['title']} ({job['source']})")
        return  # HARD STOP — guarantees 1 job only

    print("No unpublished jobs found.")

if __name__ == "__main__":
    import pickle
    main()



