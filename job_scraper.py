#!/usr/bin/env python3
"""
job_scraper.py — LOG ONLY (FIXED)
"""
import os
import json, re, hashlib, requests
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import feedparser
from bs4 import BeautifulSoup

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
LOG_FILE = DATA_DIR / "jobs_log.json"

# CATEGORY can now be multiple, comma-separated
CATEGORY = os.getenv("CATEGORY", "tech,web3,crypto").split(",")

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

def clean_text(html_text, limit=250):
    text = BeautifulSoup(html_text or "", "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)[:limit]

def detect_level(text):
    t = text.lower()
    if any(x in t for x in ["senior","lead","principal"]): return "Senior"
    if any(x in t for x in ["junior","intern","entry"]): return "Junior"
    if any(x in t for x in ["mid","intermediate"]): return "Mid"
    return "Not specified"

# ✅ Generate unique ID using link only (ignore source to avoid duplicates)
def make_id(link):
    return hashlib.md5(link.encode()).hexdigest()[:12]

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
            "id": make_id(link),
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
        for e in data.entries[:15]:
            link = getattr(e, "link", "")
            raw = getattr(e, "summary", "") or getattr(e, "description", "")
            jobs.append({
                "id": make_id(link),
                "title": getattr(e, "title", "Job"),
                "company": getattr(e, "author", urlparse(feed).netloc),
                "category": category,
                "level": detect_level(raw),
                "source": urlparse(feed).netloc,
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

    # Loop through all selected categories
    for cat in CATEGORY:
        cat = cat.strip().lower()
        new += [job for job in fetch_rss(cat) if job["id"] not in seen]

    # Add Mercor jobs only once (optional, you can loop multiple sources)
    new += [job for job in fetch_mercor() if job["id"] not in seen]

    if new:
        save_log(existing + new)
        print(f"Logged {len(new)} new jobs from {len(CATEGORY)} categories")
    else:
        print("No new jobs")

if __name__ == "__main__":
    main()


