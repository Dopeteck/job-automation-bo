#!/usr/bin/env python3

import json, os, html
from pathlib import Path
from googleapiclient.discovery import build
import pickle

LOG_FILE = Path("data/jobs_log.json")
TOKEN_FILE = "token_blogger.pkl"
BLOG_ID = os.getenv("BLOGGER_ID")

def load_jobs():
    return json.loads(LOG_FILE.read_text())

def save_jobs(jobs):
    LOG_FILE.write_text(json.dumps(jobs, indent=2))

def main():
    with open(TOKEN_FILE, "rb") as f:
        creds = pickle.load(f)

    service = build("blogger", "v3", credentials=creds)
    jobs = load_jobs()

    for job in jobs:
        pub = job.setdefault("published", {})
        if pub.get("blogger"):
            continue

        title = f"{job['title']} at {job['company']} ({job['level']})"

        content = f"""
<h2>{html.escape(job['title'])}</h2>

<p><strong>Company:</strong> {html.escape(job['company'])}</p>
<p><strong>Category:</strong> {job['category'].upper()}</p>
<p><strong>Level:</strong> {job['level']}</p>

<h3>Job Description</h3>
<p>{html.escape(job['short_desc'])}</p>

<h3>Why This Role Matters</h3>
<p>This is a remote opportunity in the {job['category']} space, ideal for professionals seeking global exposure and career growth.</p>

<p><a href="{job['link']}"><strong>👉 Apply Here</strong></a></p>

<p><em>More curated remote jobs daily on Telegram.</em></p>
"""

        service.posts().insert(
            blogId=BLOG_ID,
            body={"title": title, "content": content},
            isDraft=False
        ).execute()

        job["published"]["blogger"] = True
        save_jobs(jobs)
        print("Posted ONE job to Blogger")
        return

    print("No unpublished jobs for Blogger")

if __name__ == "__main__":
    main()








