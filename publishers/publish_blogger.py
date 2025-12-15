#!/usr/bin/env python3
import json, os, html, random
from pathlib import Path
from googleapiclient.discovery import build
import pickle

DATA = Path("data")
LOG_FILE = DATA / "jobs_log.json"
SENT_FILE = DATA / "blogger_sent.json"

BLOGGER_ID = os.getenv("BLOGGER_ID")
TOKEN_FILE = "token_blogger.pkl"

def load_json(path, default):
    if path.exists():
        return json.loads(path.read_text())
    return default

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2))

def pick_job(jobs, sent_ids):
    pool = [j for j in jobs if j["id"] not in sent_ids]
    return random.choice(pool) if pool else None

def seo_content(job):
    return f"""
<h2>{html.escape(job['title'])} – Remote Job</h2>

<p><strong>Company:</strong> {html.escape(job['company'])}</p>
<p><strong>Level:</strong> {job['level']}</p>
<p><strong>Category:</strong> {job['category'].title()}</p>

<h3>Role Overview</h3>
<p>{html.escape(job['short_desc'])}</p>

<h3>Why This Role Is Worth Applying For</h3>
<ul>
  <li>Fully remote opportunity</li>
  <li>Competitive compensation</li>
  <li>Work with a globally distributed team</li>
</ul>

<h3>How to Apply</h3>
<p>
  <a href="{job['link']}" target="_blank">
    👉 Apply for this position
  </a>
</p>

<p><em>More remote jobs posted daily.</em></p>
"""

def main():
    jobs = load_json(LOG_FILE, [])
    sent = set(load_json(SENT_FILE, []))

    job = pick_job(jobs, sent)
    if not job:
        print("No new Blogger job.")
        return

    with open(TOKEN_FILE, "rb") as f:
        creds = pickle.load(f)

    service = build("blogger", "v3", credentials=creds)

    service.posts().insert(
        blogId=BLOGGER_ID,
        body={
            "title": f"{job['title']} – Remote {job['category'].title()} Job",
            "content": seo_content(job)
        },
        isDraft=False
    ).execute()

    sent.add(job["id"])
    save_json(SENT_FILE, list(sent))
    print("Blogger post published.")

if __name__ == "__main__":
    main()





