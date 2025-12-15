#!/usr/bin/env python3
"""
Publish jobs from data/jobs_log.json to Blogger
SEO-optimized, NO OpenAI dependency
"""

import os
import json
import html
from pathlib import Path
from datetime import datetime
from googleapiclient.discovery import build
import pickle

# =========================
# CONFIG
# =========================
BLOGGER_ID = os.getenv("BLOGGER_ID")
TOKEN_FILE = "token_blogger.pkl"

LOG_FILE = Path("data/jobs_log.json")
POSTED_FILE = Path("data/blogger_posted.json")

POST_LIMIT = 1  # one strong SEO post per run

# =========================
# HELPERS
# =========================
def load_json(path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# =========================
# HTML BUILDER (SEO)
# =========================
def build_html(job):
    title = html.escape(job["title"])
    company = html.escape(job.get("company", ""))
    level = job.get("level", "Not specified")
    category = job.get("category", "Remote Jobs").title()
    desc = html.escape(job.get("short_desc", ""))

    keywords = f"{title}, {company}, remote {category}, {level} jobs"

    return f"""
<article>
  <h1>{title} ({level})</h1>

  <p><strong>Company:</strong> {company}</p>
  <p><strong>Category:</strong> {category}</p>
  <p><strong>Work Type:</strong> Fully Remote</p>

  <h2>Job Overview</h2>
  <p>{desc}</p>

  <h2>Why This Role Matters</h2>
  <p>
    This {level.lower()} role at {company} is ideal for professionals seeking
    long-term growth, competitive compensation, and the flexibility of remote work.
  </p>

  <h2>Who Should Apply</h2>
  <ul>
    <li>Experienced professionals in {category}</li>
    <li>Candidates seeking fully remote opportunities</li>
    <li>People looking for career stability and growth</li>
  </ul>

  <h2>How to Apply</h2>
  <p>
    👉 <a href="{job['link']}" target="_blank" rel="noopener">
    Apply directly on the company website
    </a>
  </p>

  <hr/>

  <p><strong>Looking for more jobs?</strong><br/>
  Join our Telegram channel and get daily remote job alerts.</p>

  <meta name="keywords" content="{keywords}">
</article>
"""

# =========================
# MAIN
# =========================
def main():
    if not BLOGGER_ID:
        raise RuntimeError("BLOGGER_ID missing")

    jobs = load_json(LOG_FILE, [])
    posted = set(load_json(POSTED_FILE, []))

    with open(TOKEN_FILE, "rb") as f:
        creds = pickle.load(f)

    service = build("blogger", "v3", credentials=creds)

    count = 0
    new_posted = []

    for job in jobs:
        if job["id"] in posted:
            continue

        content = build_html(job)

        service.posts().insert(
            blogId=BLOGGER_ID,
            body={
                "title": f"{job['title']} – Remote {job.get('level','')} Job",
                "content": content
            },
            isDraft=False
        ).execute()

        new_posted.append(job["id"])
        count += 1

        if count >= POST_LIMIT:
            break

    if new_posted:
        save_json(POSTED_FILE, list(posted.union(new_posted)))

    print(f"Blogger: published {count} post(s)")

if __name__ == "__main__":
    main()



