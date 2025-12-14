#!/usr/bin/env python3
"""
job_scraper.py — LOG ONLY (PRODUCTION SAFE)
Scrapes jobs and appends to data/jobs_log.json
NO posting. NO AI. NO publishers.
"""

import os
import json
import re
import requests
import hashlib
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
    if not LOG_FILE.exists():
        return []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        print("⚠️ Corrupted jobs_log.json — resetting")
        return []

def save_log(entries):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)

def clean_text(html, limit=180):
    text = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text[:limit]

def detect_level(text):
    t = (text or "").lower()
    if any(k in t for k in ["senior", "lead", "principal"]):
        return "Senior"
    if any(k in t for k in ["junior", "entry", "intern"]):
        return "Junior"
    if any(k in t for k in ["mid", "intermediate"]):
        return "Mid-level"
    return "Not specified"

def make_id(source, link):
    h = hashlib.md5(link.encode("utf-8")).hexdigest()[:10]
    return f"{source}_{h}"

def normalize_source(feed_url):
    domain = urlparse(feed_url).netloc
    if "remoteok" in domain:
        return "RemoteOK"
    if "weworkremotely" in domain:
        return "WeWorkRemotely"
    if "remotive" in domain:
        return "Remotive"
    if "cryptojobslist" in domain:
        return "CryptoJobsList"
    if "web3.career" in domain:
        return "Web3Career"
    if "crypto.jobs" in domain:
        return "CryptoJobs"
    return domain

# =========================
# MERCOR
# =========================
def fetch_mercor():
    url = "https://api.mercor.com/api/jobs/public"
    try:
        r = requests.get(url, timeout=15)
        data = r.json()
    except Exception:
        return []

    jobs = []
    for j in data.get("jobs", [])[:10]:
        desc = j.get("description", "")
        slug = j.get("slug")
        if not slug:
            continue

        link = f"https://www.mercor.com/jobs/{slug}"

        jobs.append({
            "id": make_id("mercor", link),
            "title": j.get("title", "Job"),
            "company": "Mercor",
            "category": CATEGORY,
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
        parsed = feedparser.parse(feed)
        source_name = normalize_source(feed)

        for e in parsed.entries[:10]:
            link = getattr(e, "link", None)
            if not link:
                continue

            raw = getattr(e, "summary", "") or getattr(e, "description", "")
            company = getattr(e, "author", "") or source_name

            jobs.append({
                "id": make_id(source_name.lower(), link),
                "title": getattr(e, "title", "Job"),
                "company": company,
                "category": category,
                "level": detect_level(raw),
                "source": source_name,
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
    print(f"✅ Logged {len(new_jobs)} new jobs.")

if __name__ == "__main__":
    main()
