#!/usr/bin/env python3

import json, pickle, os
from pathlib import Path
from googleapiclient.discovery import build

BLOGGER_ID = os.getenv("BLOGGER_ID")

DATA = Path("../data/jobs_log.json")
SENT = Path("data/blogger_sent.json")
TOKEN = "token_blogger.pkl"

def load(p): return json.load(open(p)) if p.exists() else []
def save(p,d): json.dump(d, open(p,"w"), indent=2)

def main():
    with open(TOKEN,"rb") as f:
        creds = pickle.load(f)

    service = build("blogger","v3",credentials=creds)

    jobs = load(DATA)
    sent = set(load(SENT))

    for j in jobs:
        if j["id"] in sent:
            continue

        content = f"""
<h3>{j['title']}</h3>
<p><b>Company:</b> {j['company']}</p>
<p><b>Level:</b> {j['level']}</p>
<p>{j['short_desc']}</p>
<p><a href="{j['link']}">👉 Apply here</a></p>
"""

        service.posts().insert(
            blogId=BLOGGER_ID,
            body={"title": j["title"], "content": content},
            isDraft=False
        ).execute()

        sent.add(j["id"])
        break   # one post per run

    save(SENT, list(sent))
    print("Blogger post published.")

if __name__ == "__main__":
    main()
