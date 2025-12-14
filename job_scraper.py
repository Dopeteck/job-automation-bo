#!/usr/bin/env python3
"""
job_scraper.py — LOG ONLY
Scrapes jobs and appends to data/jobs_log.json
"""

import os, json, re, requests, hashlib
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import feedparser
from bs4 import BeautifulSoup

# =========================
# CONFIG
# =========================
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
LOG_FILE = DATA_DIR / "jobs_log.json"

CATEGORY = os.getenv("CATEGORY", "tech")

# =========================
# FEEDS
# =========================
FEEDS = {
    "tech": [
        "https://remoteok.com/remote-jobs.rss",
        "https://weworkremotely.com/remote-jobs.rss",
        "https://remotive.io/remote-jobs/feed"
    ],
    "web3": [
        "https://web3.career/rss",
        "https://cryptojobslist.com/jobs.rss"
    ],
    "crypto": [
        "https://crypto.jobs/rss",
        "https://cryptojobslist.com/jobs.rss"
    ]
}

# =========================
# HELPERS
# =========================
def load_log():
    if LOG_FILE.exists():
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_log(entries):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)

def clean_text(html, limit=160):
    text = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text[:limit]

def detect_level(text):
    t = text.lower()
    if any(k in t for k in ["senior", "lead", "principal"]): return "Senior"
    if any(k in t for k in ["junior", "entry", "intern"]): return "Junior"
    if any(k in t for k in ["mid", "intermediate"]): return "Mid-level"
    return "Not specified"

def make_id(source, link):
    h = hashlib.md5(link.encode()).hexdigest()[:8]
    return f"{source}_{h}"

# =========================
# MERCOR
# =========================
def fetch_mercor():
    url = "https://api.mercor.com/api/jobs/public"
    try:
        r = requests.get(url, timeout=15)
        data = r.json()
    except:
        return []

    jobs = []
    for j in data.get("jobs", [])[:10]:
        desc = j.get("description", "")
        link = f"https://www.mercor.com/jobs/{j['slug']}"
        jobs.append({
            "id": make_id("mercor", link),
            "title": j.get("title"),
            "company": "Mercor",
            "category": "tech",
            "level": detect_level(desc),
            "source": "Mercor",
            "link": link,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "short_desc": clean_text(desc)
        })
    return jobs

# =========================
# RSS
# =========================
def fetch_rss(category):
    jobs = []
    for feed in FEEDS.get(category, []):
        data = feedparser.parse(feed)
        source = urlparse(feed).netloc.split(".")[0]
        for e in data.entries[:10]:
            link = getattr(e, "link", "")
            raw = getattr(e, "summary", "") or getattr(e, "description", "")
            jobs.append({
                "id": make_id(source, link),
                "title": getattr(e, "title", "Job"),
                "company": getattr(e, "author", ""),
                "category": category,
                "level": detect_level(raw),
                "source": source,
                "link": link,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "short_desc": clean_text(raw)
            })
    return jobs

# =========================
# MAIN
# =========================
def main():
    existing = load_log()
    seen_ids = {j["id"] for j in existing}

    new_jobs = []
    for job in fetch_mercor() + fetch_rss(CATEGORY):
        if job["id"] not in seen_ids:
            new_jobs.append(job)

    if not new_jobs:
        print("No new jobs found.")
        return

    save_log(existing + new_jobs)
    print(f"Logged {len(new_jobs)} new jobs.")

if __name__ == "__main__":
    main()
