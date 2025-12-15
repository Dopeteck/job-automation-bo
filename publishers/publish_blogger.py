#!/usr/bin/env python3

import json, os, html, pickle
from pathlib import Path
from googleapiclient.discovery import build

DATA = Path("data")
LOG_FILE = DATA / "jobs_log.json"
SENT_FILE = DATA / "sent_blogger.json"
TOKEN = "token_blogger.pkl"

BLOGGER_ID = os.getenv("BLOGGER_ID")

DATA.mkdir(exist_ok=True)

def load_json(path, default):
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        return json.loads(path.read_text())
    except:
        return default

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2))

def main():
    jobs = load_json(LOG_FILE, [])
    sent = set(load_json(SENT_FILE, []))

    job = next((j for j in jobs if j["id"] not in sent), None)

    if not job:
        print("No new Blogger jobs.")
        return

    with open(TOKEN, "rb") as f:
        creds = pickle.load(f)

    service = build("blogger", "v3", credentials=creds)

    seo_title = f"{job['title']} at {job['company']} – Remote {job['level']} Role"

    content = f"""
<h1>{html.escape(job['title'])}</h1>

<p><strong>Company:</strong> {html.escape(job['company'])}</p>
<p><strong>Level:</strong> {job['level']}</p>
<p><strong>Category:</strong> {job['category'].title()}</p>

<h2>Job Description</h2>
<p>{html.escape(job['short_desc'])}</p>

<h2>Why This Role Is Worth Applying For</h2>
<ul>
<li>Fully remote opportunity</li>
<li>Competitive compensation</li>
<li>High-growth team</li>
</ul>

<p>
<a href="{job['link']}">
<strong>👉 Apply for this remote role here</strong>
</a>
</p>

<p><em>More verified remote jobs posted daily.</em></p>
"""

    service.posts().insert(
        blogId=BLOGGER_ID,
        body={"title": seo_title, "content": content},
        isDraft=False
    ).execute()

    sent.add(job["id"])
    save_json(SENT_FILE, list(sent))
    print("Blogger post published.")

if __name__ == "__main__":
    main()







