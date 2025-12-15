#!/usr/bin/env python3

import json, html, pickle, os
from pathlib import Path
from googleapiclient.discovery import build

LOG_FILE = Path("data/jobs_log.json")
BLOGGER_ID = os.getenv("BLOGGER_ID")
TOKEN_FILE = "token_blogger.pkl"

def main():
    jobs = json.loads(LOG_FILE.read_text())

    with open(TOKEN_FILE,"rb") as f:
        creds = pickle.load(f)

    service = build("blogger","v3",credentials=creds)

    for job in jobs:
        if job["published_blogger"]:
            continue

        body = f"""
<h2>{html.escape(job['title'])} – Remote Job</h2>
<p><b>Company:</b> {html.escape(job['company'])}</p>
<p><b>Level:</b> {job['level']}</p>
<p>{html.escape(job['short_desc'])}</p>
<p><a href="{job['link']}">👉 Apply here</a></p>
"""

        service.posts().insert(
            blogId=BLOGGER_ID,
            body={"title": job["title"], "content": body},
            isDraft=False
        ).execute()

        job["published_blogger"] = True
        LOG_FILE.write_text(json.dumps(jobs, indent=2))
        break  # ✅ ONE POST ONLY

if __name__ == "__main__":
    main()









