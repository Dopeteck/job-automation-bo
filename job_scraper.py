#!/usr/bin/env python3
"""
job_scraper.py — LOG ONLY (FINAL)
"""

import json, re, hashlib, requests
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import feedparser
from bs4 import BeautifulSoup

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
LOG_FILE = DATA_DIR / "jobs_log.json"

CATEGORY = os.getenv("CATEGORY", "tech")

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

def load_log():
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text())
    return []

def save_log(data):
    LOG_FILE.write_text(json.dumps(data, indent=2))

def clean_text(html, limit=250):
    text = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)[:limit]

def detect_level(text):
    t = text.lower()
    if any(x in t for x in ["senior","lead","principal"]): return "Senior"
    if any(x in t for x in ["junior","intern","entry"]): return "Junior"
    if any(x in t for x in ["mid","intermediate"]): return "Mid"
    return "Not specified"

def make_id(source, link):
    return f"{source}_{hashlib.md5(link.encode()).hexdigest()[:8]}"

def fetch_mercor():
    url = "https://api.mercor.com/api/jobs/public"
    try:
        data = requests.get(url, timeout=15).json()
    except:
        return []

    jobs = []
    for j in data.get("jobs", [])[:15]:
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
            "short_desc": clean_text(desc),
            "published_telegram": False,
            "published_blogger": False
        })
    return jobs

def fetch_rss(category):
    jobs = []
    for feed in FEEDS.get(category, []):
        data = feedparser.parse(feed)
        source = urlparse(feed).netloc.split(".")[0]
        for e in data.entries[:15]:
            link = getattr(e, "link", "")
            raw = getattr(e, "summary", "") or getattr(e, "description", "")
            jobs.append({
                "id": make_id(source, link),
                "title": getattr(e, "title", "Job"),
                "company": getattr(e, "author", source),
                "category": category,
                "level": detect_level(raw),
                "source": source,
                "link": link,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "short_desc": clean_text(raw),
                "published_telegram": False,
                "published_blogger": False
            })
    return jobs

def main():
    existing = load_log()
    seen = {j["id"] for j in existing}

    new = []
    for job in fetch_mercor() + fetch_rss(CATEGORY):
        if job["id"] not in seen:
            new.append(job)

    if new:
        save_log(existing + new)
        print(f"Logged {len(new)} jobs")
    else:
        print("No new jobs")

if __name__ == "__main__":
    main()

