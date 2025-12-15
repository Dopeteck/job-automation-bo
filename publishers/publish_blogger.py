#!/usr/bin/env python3
"""
Blogger Publisher
- SEO-optimized long-form content
- Zero repetition
- Google-friendly structure
"""

import json, os, html, pickle
from pathlib import Path
from googleapiclient.discovery import build

DATA_FILE = Path("data/jobs_log.json")
TOKEN_FILE = "token_blogger.pkl"
BLOG_ID = os.getenv("BLOGGER_ID")

def load_jobs():
    if not DATA_FILE.exists():
        return []
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))

def save_jobs(jobs):
    DATA_FILE.write_text(json.dumps(jobs, indent=2), encoding="utf-8")

def blogger_service():
    with open(TOKEN_FILE, "rb") as f:
        creds = pickle.load(f)
    return build("blogger", "v3", credentials=creds)

def seo_post(job):
    title = f"{job['title']} at {job['company']} (Remote)"

    body = f"""
<h1>{html.escape(job['title'])} – Remote Job</h1>

<p><strong>Company:</strong> {html.escape(job['company'])}</p>
<p><strong>Experience Level:</strong> {job['level']}</p>
<p><strong>Category:</strong> {job['category'].title()}</p>

<h2>Job Overview</h2>
<p>{html.escape(job['short_desc'])}</p>

<h2>Why This Role Is Worth Applying For</h2>
<ul>
  <li>Fully remote opportunity</li>
  <li>Competitive compensation</li>
  <li>Career growth in a fast-moving team</li>
</ul>

<h2>How to Apply</h2>
<p>
👉 <a href="{job['link']}" rel="nofollow noopener" target="_blank">
Apply directly on the company website
</a>
</p>

<hr />
<p>
📌 <em>More remote tech, Web3, and crypto jobs are posted daily.</em><br />
Join our Telegram for instant alerts.
</p>
"""

    return title, body

def main():
    service = blogger_service()
    jobs = load_jobs()
    published_count = 0

    for job in jobs:
        published = job.setdefault("published", {})
        if published.get("blogger"):
            continue

        title, body = seo_post(job)

        service.posts().insert(
            blogId=BLOG_ID,
            body={
                "title": title,
                "content": body
            },
            isDraft=False
        ).execute()

        published["blogger"] = True
        published_count += 1

        if published_count >= 2:  # SEO pacing
            break

    save_jobs(jobs)
    print(f"Blogger: published {published_count} posts")

if __name__ == "__main__":
    main()




