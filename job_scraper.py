#!/usr/bin/env python3
"""
job_scraper.py — LOG ONLY (FINAL, DEDUP SAFE)
- Canonical URL normalization
- Stable UID generation
- Prevents RemoteOK reposts permanently
"""

import os
import json
import re
import hashlib
import requests
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import feedparser
from bs4 import BeautifulSoup

# -----------------------
# PATHS / CONFIG
# -----------------------
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
LOG_FILE = DATA_DIR / "jobs_log.json"

CATEGORY = os.getenv("CATEGORY", "tech,web3,crypto").split(",")

FEEDS = {
    "tech": [
        "https://remoteok.com/remote-jobs.rss",
        "https://weworkremotely.com/remote-jobs.rss",
        "https://remotive.io/remote-jobs/feed",
    ],
    "web3": [
        "https://web3.career/rss",
        "https://cryptojobslist.com/jobs.rss",
    ],
    "crypto": [
        "https://crypto.jobs/rss",
        "https://cryptojobslist.com/jobs.rss",
    ],
}

# -----------------------
# UTILITIES
# -----------------------
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
    t = (text or "").lower()
    if any(x in t for x in ["senior", "lead", "principal"]):
        return "Senior"
    if any(x in t for x in ["junior", "intern", "entry"]):
        return "Junior"
    if any(x in t for x in ["mid", "intermediate"]):
        return "Mid"
    return "Not specified"

# -----------------------
# 🔐 DEDUP CORE (CRITICAL)
# -----------------------
def canonical_link(link: str) -> str:
    """
    Remove query params, fragments, trailing slashes.
    Fixes RemoteOK duplication.
    """
    p = urlparse(link)
    return urlunparse((p.scheme, p.netloc, p.path.rstrip("/"), "", "", ""))

def make_id(source, title, company, link):
    clean = canonical_link(link)
    raw = f"{source}|{title}|{company}|{clean}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

# -----------------------
# SOURCES
# -----------------------
def fetch_mercor():
    url = "https://api.mercor.com/api/jobs/public"
    try:
        data = requests.get(url, timeout=15).json()
    except Exception:
        return []

    jobs = []
    for j in data.get("jobs", [])[:15]:
        desc = j.get("description", "")
        link = f"https://www.mercor.com/jobs/{j['slug']}"
        jobs.append({
            "id": make_id("mercor", j.get("title"), "Mercor", link),
            "title": j.get("title"),
            "company": "Mercor",
            "category": "tech",
            "level": detect_level(desc),
            "source": "Mercor",
            "link": canonical_link(link),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "short_desc": clean_text(desc),
            "published_telegram": False,
            "published_blogger": False,
        })
    return jobs

def fetch_rss(category):
    jobs = []
    for feed in FEEDS.get(category, []):
        data = feedparser.parse(feed)
        source = urlparse(feed).netloc

        for e in data.entries[:15]:
            link = getattr(e, "link", "")
            raw = getattr(e, "summary", "") or getattr(e, "description", "")
            title = getattr(e, "title", "Job")
            company = getattr(e, "author", source)

            jobs.append({
                "id": make_id(source, title, company, link),
                "title": title,
                "company": company,
                "category": category,
                "level": detect_level(raw),
                "source": source,
                "link": canonical_link(link),
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "short_desc": clean_text(raw),
                "published_telegram": False,
                "published_blogger": False,
            })
    return jobs

# -----------------------
# MAIN
# -----------------------
def main():
    existing = load_log()
    seen_ids = {j["id"] for j in existing}

    new_jobs = []

    for cat in CATEGORY:
        cat = cat.strip().lower()
        new_jobs.extend(
            job for job in fetch_rss(cat) if job["id"] not in seen_ids
        )

    new_jobs.extend(
        job for job in fetch_mercor() if job["id"] not in seen_ids
    )

    if new_jobs:
        save_log(existing + new_jobs)
        print(f"✅ Logged {len(new_jobs)} new jobs")
    else:
        print("ℹ️ No new jobs found")

if __name__ == "__main__":
    main()
