#!/usr/bin/env python3
"""
Blogger Publisher — SEO & Long-form
"""

import os, json, html, pickle
from pathlib import Path
from openai import OpenAI
from googleapiclient.discovery import build

DATA_PATH = Path("data/jobs_log.json")
POSTED_PATH = Path("data/blogger_posted.json")
TOKEN_FILE = "token_blogger.pkl"

BLOGGER_ID = os.getenv("BLOGGER_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

def load_json(path, default):
    if path.exists():
        return json.loads(path.read_text())
    return default

def save_json(path, data):
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2))

def ai_summary(job):
    prompt = f"""
Write a helpful job overview in bullet points.

Include:
- What you'll do
- Who it's for
- Why it's interesting

Job:
Title: {job['title']}
Company: {job['company']}
Description: {job.get('short_desc','')}
"""
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}],
        max_tokens=180
    )
    return r.choices[0].message.content.strip()

def build_html(job, summary):
    bullets = "".join(
        f"<li>{html.escape(x)}</li>"
        for x in summary.splitlines() if x.strip()
    )

    return f"""
<h2>{html.escape(job['title'])}</h2>

<p><b>Company:</b> {html.escape(job['company'])}</p>
<p><b>Level:</b> {job.get('level','Not specified')}</p>

<h3>Why this role stands out</h3>
<ul>{bullets}</ul>

<p>
<a href="{job['link']}">
👉 Apply directly here
</a>
</p>

<hr>
<p><i>More curated remote jobs daily on Telegram.</i></p>
"""

def main():
    jobs = load_json(DATA_PATH, [])
    posted = set(load_json(POSTED_PATH, []))

    with open(TOKEN_FILE, "rb") as f:
        creds = pickle.load(f)

    service = build("blogger", "v3", credentials=creds)

    for job in reversed(jobs):
        if job["id"] in posted:
            continue

        summary = ai_summary(job)
        content = build_html(job, summary)

        service.posts().insert(
            blogId=BLOGGER_ID,
            body={
                "title": f"{job['title']} at {job['company']} (Remote)",
                "content": content
            },
            isDraft=False
        ).execute()

        posted.add(job["id"])
        save_json(POSTED_PATH, list(posted))
        break  # ONE post per run

if __name__ == "__main__":
    main()

