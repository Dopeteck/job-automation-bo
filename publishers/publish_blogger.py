#!/usr/bin/env python3
"""
Publish jobs from data/jobs_log.json to Blogger
"""

import os
import json
import html
import pickle
from pathlib import Path
from googleapiclient.discovery import build

# =========================
# CONFIG
# =========================
BLOGGER_ID = os.getenv("BLOGGER_ID")

LOG_FILE = Path("data/jobs_log.json")
POSTED_FILE = Path("data/blogger_posted.json")
TOKEN_FILE = Path("token_blogger.pkl")

POST_LIMIT = 1  # Blogger = quality over quantity

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
# MAIN
# =========================
def main():
    if not BLOGGER_ID:
        raise RuntimeError("BLOGGER_ID not set")

    jobs = load_json(LOG_FILE, [])
    posted = set(load_json(POSTED_FILE, []))

    with open(TOKEN_FILE, "rb") as f:
        creds = pickle.load(f)

    service = build("blogger", "v3", credentials=creds)

    sent = 0
    new_posted = []

    for job in jobs:
        if job["id"] in posted:
            continue

        content = f"""
<h3>{html.escape(job['title'])}</h3>
<p><b>Company:</b> {html.escape(job.get('company',''))}</p>
<p><b>Level:</b> {job.get('level','Not specified')}</p>
<p>{html.escape(job.get('short_desc',''))}</p>
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

        new_posted.append(job["id"])
        sent += 1

        if sent >= POST_LIMIT:
            break

    if new_posted:
        save_json(POSTED_FILE, list(posted.union(new_posted)))

    print(f"Blogger: posted {sent} jobs")

if __name__ == "__main__":
    main()


