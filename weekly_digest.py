#!/usr/bin/env python3

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import pickle

import openai
from googleapiclient.discovery import build

# --------------------
# CONFIG
# --------------------
LOG_PATH = Path("data/jobs_log.json")
OUTPUT_MD = Path("weekly_digest.md")

CATEGORIES = ["tech", "web3", "crypto"]

openai.api_key = os.getenv("OPENAI_API_KEY")

GOOGLE_TOKEN_FILE = "token_blogger.pkl"

# --------------------
# LOAD RECENT JOBS
# --------------------
def load_recent_jobs(days=7):
    if not LOG_PATH.exists():
        return []

    with open(LOG_PATH, "r", encoding="utf-8") as f:
        jobs = json.load(f)

    cutoff = datetime.utcnow() - timedelta(days=days)

    return [
        j for j in jobs
        if datetime.fromisoformat(j["timestamp"].replace("Z", "")) >= cutoff
    ]

# --------------------
# AI SUMMARY (PER CATEGORY)
# --------------------
def ai_category_summary(category, jobs):
    if not jobs:
        return ""

    prompt = f"""
Summarize this week's {category} jobs in 3 bullet points.
Explain who these roles are best for.

Jobs:
""" + "\n".join([f"- {j['title']} at {j['company']}" for j in jobs[:10]])

    try:
        res = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=150
        )
        return res.choices[0].message.content.strip()
    except Exception as e:
        print("AI summary failed:", e)
        return ""

# --------------------
# BUILD DIGEST
# --------------------
def build_digest(jobs):
    lines = []

    lines.append("# 🚀 Weekly Remote Jobs Digest\n")
    lines.append(
        "Hand-picked tech, Web3 & crypto roles — no spam, no repost loops.\n\n"
    )

    for cat in CATEGORIES:
        cat_jobs = [j for j in jobs if j["category"] == cat]
        if not cat_jobs:
            continue

        lines.append(f"## {cat.upper()} JOBS\n")

        ai_summary = ai_category_summary(cat, cat_jobs)
        if ai_summary:
            lines.append(f"🧠 **AI Insight**\n{ai_summary}\n\n")

        for j in cat_jobs[:7]:
            lines.append(
                f"**{j['title']} — {j['company']}**  \n"
                f"- {j['level']}  \n"
                f"- Source: {j['source']}  \n"
                f"👉 Apply: {j['link']}\n\n"
            )

    lines.append(
        "---\n\n"
        "💡 *Tip:* Update your resume before applying. "
        "Top resume + AI tools linked inside.\n\n"
        "📬 Daily jobs on Telegram → @YourChannel"
    )

    return "\n".join(lines)

# --------------------
# GOOGLE DOCS EXPORT
# --------------------
def send_to_google_docs(title, content):
    if not os.path.exists(GOOGLE_TOKEN_FILE):
        print("Google token not found, skipping Docs export.")
        return

    with open(GOOGLE_TOKEN_FILE, "rb") as f:
        creds = pickle.load(f)

    service = build("docs", "v1", credentials=creds)

    doc = service.documents().create(
        body={"title": title}
    ).execute()

    doc_id = doc["documentId"]

    service.documents().batchUpdate(
        documentId=doc_id,
        body={
            "requests": [{
                "insertText": {
                    "location": {"index": 1},
                    "text": content
                }
            }]
        }
    ).execute()

    print(f"Google Doc created:")
    print(f"https://docs.google.com/document/d/{doc_id}")

# --------------------
# MAIN
# --------------------
def main():
    jobs = load_recent_jobs(7)

    if not jobs:
        print("No jobs found for digest.")
        return

    digest = build_digest(jobs)

    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write(digest)

    print(f"Weekly digest saved → {OUTPUT_MD.resolve()}")

    send_to_google_docs(
        title="Weekly Remote Jobs Digest",
        content=digest
    )

if __name__ == "__main__":
    main()
