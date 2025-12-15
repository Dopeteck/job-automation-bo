#!/usr/bin/env python3

import json, os, html
from pathlib import Path
from googleapiclient.discovery import build
import pickle

DATA_FILE = Path("data/jobs_log.json")
SENT_FILE = Path("data/sent_blogger.json")
TOKEN_FILE = "token_blogger.pkl"
BLOG_ID = os.getenv("BLOGGER_ID")

def load_json_safe(path, default):
    try:
        if not path.exists():
            return default
        text = path.read_text().strip()
        if not text:
            return default
        return json.loads(text)
    except Exception:
        return default

def save_json(path, data):
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2))

def main():
    jobs = load_json_safe(DATA_FILE, [])
    sent = set(load_json_safe(SENT_FILE, []))

    job = next((j for j in jobs if j["id"] not in sent), None)
    if not job:
        print("No new Blogger jobs.")
        return

    with open(TOKEN_FILE, "rb") as f:
        creds = pickle.load(f)

    service = build("blogger", "v3", credentials=creds)

    title = f"{job['title']} at {job['company']} ({job['level']}) – Remote Job"

    content = f"""
<h2>{html.escape(job['title'])} – Remote {html.escape(job['level'])} Role</h2>

<p><strong>Company:</strong> {html.escape(job['company'])}</p>
<p><strong>Category:</strong> {job['category'].title()}</p>

<h3>About the Role</h3>
<p>{html.escape(job['short_desc'])}</p>

<h3>Why This Job Is Worth Applying For</h3>
<ul>
  <li>100% remote opportunity</li>
  <li>Competitive compensation</li>
  <li>Work with a global team</li>
</ul>

<h3>How to Apply</h3>
<p>
<a href="{job['link']}" rel="nofollow noopener" target="_blank">
👉 Apply directly on the company website
</a>
</p>

<p><em>Looking for more remote tech, Web3 & crypto jobs? Subscribe for weekly digests.</em></p>
"""

    service.posts().insert(
        blogId=BLOG_ID,
        body={"title": title, "content": content},
        isDraft=False
    ).execute()

    sent.add(job["id"])
    save_json(SENT_FILE, list(sent))

    print("Blogger posted:", title)

if __name__ == "__main__":
    main()






