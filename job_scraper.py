#!/usr/bin/env python3
"""
job_scraper.py

One-shot job scraper & publisher (production-ready)
- Multi-source jobs (RemoteOK, Remotive, WWR, Web3, Crypto, Mercor)
- Mercor + generic referral injection
- AI job summaries (optional)
- Blogger + Telegram posting
- Prepopulate + scheduled mode
"""

import os
import time
import pickle
import html
import re
import traceback
import requests
from datetime import datetime
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

import feedparser
from bs4 import BeautifulSoup

# =========================
# ENV / CONFIG
# =========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL")
BLOGGER_ID = os.getenv("BLOGGER_ID")

CATEGORY = os.getenv("CATEGORY")
MANUAL = os.getenv("MANUAL", "0") == "1"
FORCE_PREPOPULATE = os.getenv("FORCE_PREPOPULATE", "0") == "1"

REF_MERCOR = os.getenv("REF_MERCOR")
REF_GENERIC = os.getenv("REF_GENERIC")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SENT_STORE = "sent_jobs.pkl"
TOKEN_FILE = "token_blogger.pkl"

# =========================
# JOB FEEDS (BALANCED)
# =========================
FEEDS = {
    "tech": [
        "https://remoteok.com/remote-jobs.rss",
        "https://weworkremotely.com/remote-jobs.rss",
        "https://remotive.io/remote-jobs/feed"
    ],
    "web3": [
        "https://web3.career/rss",
        "https://cryptojobslist.com/jobs.rss",
        "https://remotive.io/remote-jobs/blockchain/feed"
    ],
    "crypto": [
        "https://crypto.jobs/rss",
        "https://cryptojobslist.com/jobs.rss",
        "https://remotive.io/remote-jobs/blockchain/feed"
    ],
    "mercor": [
        "https://work.mercor.com/"
    ]
}

REFERRAL_SITES = {
    "mercor.com": (REF_MERCOR, "ref"),
    "work.mercor.com": (REF_MERCOR, "ref"),
    "remoteok.com": (REF_GENERIC, "ref"),
    "weworkremotely.com": (REF_GENERIC, "ref"),
    "remotive.io": (REF_GENERIC, "ref")
}

ALLOWED_TAGS = ["p","br","b","strong","i","em","ul","ol","li","a","h3"]

# =========================
# STATE
# =========================
def load_sent_jobs():
    if os.path.exists(SENT_STORE):
        try:
            with open(SENT_STORE, "rb") as f:
                return pickle.load(f)
        except:
            pass
    return set()

def save_sent_jobs(s):
    with open(SENT_STORE, "wb") as f:
        pickle.dump(s, f)

sent_jobs = load_sent_jobs()

# =========================
# HELPERS
# =========================
def sanitize_html(html_text):
    soup = BeautifulSoup(html_text or "", "html.parser")
    for bad in soup(["script","style"]):
        bad.decompose()
    for tag in soup.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()
        else:
            tag.attrs = {}
    return str(soup)

def clean_text(html_text, maxlen=900):
    text = BeautifulSoup(html_text or "", "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+"," ",text)
    return text[:maxlen]

def detect_seniority(text):
    t = text.lower()
    if any(k in t for k in ["senior","lead","principal","5+"]):
        return "Senior"
    if any(k in t for k in ["junior","entry","intern"]):
        return "Junior"
    if any(k in t for k in ["mid","intermediate","3+"]):
        return "Mid-level"
    return "Not specified"

def apply_referral(url):
    if not url:
        return url
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    for dom,(code,param) in REFERRAL_SITES.items():
        if dom in domain and code:
            q = dict(parse_qsl(parsed.query))
            if param not in q:
                q[param] = code
            return urlunparse(parsed._replace(query=urlencode(q)))

    return url

# =========================
# AI SUMMARY (OPTIONAL)
# =========================
def ai_summary(title, company, desc):
    if not OPENAI_API_KEY:
        return None
    try:
        import openai
        openai.api_key = OPENAI_API_KEY

        prompt = f"""
Summarize this job in 3 short bullet points.
Be concise and attractive.

Title: {title}
Company: {company}
Description:
{desc}
"""
        r = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":prompt}],
            max_tokens=120
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        print("[AI] failed:", e)
        return None

# =========================
# BLOGGER
# =========================
def post_to_blogger(job):
    from googleapiclient.discovery import build
    with open(TOKEN_FILE,"rb") as f:
        creds = pickle.load(f)

    service = build("blogger","v3",credentials=creds)

    content = f"""
<h3>{html.escape(job['title'])}</h3>
<p><b>Company:</b> {html.escape(job['company'])}</p>
<p><b>Seniority:</b> {job['level']}</p>
"""

    if job.get("ai_summary"):
        content += "<p><b>🤖 AI Summary</b></p><ul>"
        for line in job["ai_summary"].splitlines():
            if line.strip():
                content += f"<li>{html.escape(line)}</li>"
        content += "</ul>"

    content += f"""
{job['html_description']}
<p><b>Apply:</b> <a href="{job['link']}">Apply Here</a></p>
"""

    service.posts().insert(
        blogId=BLOGGER_ID,
        body={"title":job["title"],"content":content},
        isDraft=False
    ).execute()

    time.sleep(8)

# =========================
# TELEGRAM
# =========================
def post_to_telegram(job):
    from telegram import Bot
    from telegram.parsemode import ParseMode

    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    text = (
        f"<b>🔥 NEW JOB</b>\n\n"
        f"<b>Role:</b> {html.escape(job['title'])}\n"
        f"<b>Company:</b> {html.escape(job['company'])}\n"
        f"<b>Seniority:</b> {job['level']}\n\n"
    )

    if job.get("ai_summary"):
        text += f"<b>🤖 Quick Summary</b>\n{html.escape(job['ai_summary'])}\n\n"

    text += f"<b>Apply:</b> <a href='{job['link']}'>Apply Here</a>"

    bot.send_message(
        chat_id=TELEGRAM_CHANNEL,
        text=text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=False
    )

# =========================
# FETCH JOB
# =========================
def fetch_one_job(category):
    for feed in FEEDS.get(category,[]):

        # Reduce RemoteOK dominance
        if "remoteok.com" in feed and datetime.utcnow().minute % 2 != 0:
            continue

        # Mercor scraping
        if "mercor" in feed:
            r = requests.get(feed,headers={"User-Agent":"jobbot"},timeout=15)
            soup = BeautifulSoup(r.text,"html.parser")
            for a in soup.find_all("a",href=True):
                if "job" in a["href"].lower():
                    link = apply_referral(a["href"])
                    if link in sent_jobs:
                        continue
                    title = a.get_text(strip=True) or "Mercor Role"
                    job = {
                        "title": title,
                        "company": "Mercor",
                        "link": link,
                        "html_description": "",
                        "plain_description": title
                    }
                    job["level"] = detect_seniority(title)
                    job["ai_summary"] = ai_summary(title,"Mercor",title)
                    return job
            continue

        data = feedparser.parse(feed)
        for e in data.entries:
            link = apply_referral(getattr(e,"link",None))
            if not link or link in sent_jobs:
                continue

            raw = getattr(e,"summary","") or getattr(e,"description","")
            plain = clean_text(raw)

            job = {
                "title": getattr(e,"title","Job"),
                "company": getattr(e,"author",""),
                "link": link,
                "html_description": sanitize_html(raw),
                "plain_description": plain
            }
            job["level"] = detect_seniority(plain)
            job["ai_summary"] = ai_summary(job["title"],job["company"],plain)
            return job
    return None

# =========================
# PREPOPULATE
# =========================
def prepopulate(n=9):
    if sent_jobs and not FORCE_PREPOPULATE:
        return
    count = 0
    cats = ["tech","web3","crypto"]
    i = 0
    while count < n and i < n*5:
        job = fetch_one_job(cats[i % 3])
        if job:
            sent_jobs.add(job["link"])
            save_sent_jobs(sent_jobs)
            post_to_blogger(job)
            post_to_telegram(job)
            count += 1
        i += 1

# =========================
# MAIN
# =========================
def fallback_category():
    h = datetime.utcnow().hour
    if 11 <= h <= 13: return "tech"
    if 15 <= h <= 17: return "web3"
    if 19 <= h <= 21: return "crypto"
    return "tech"

def main():
    if MANUAL:
        prepopulate(9)
        for c in ["tech","web3","crypto"]:
            job = fetch_one_job(c)
            if job:
                sent_jobs.add(job["link"])
                save_sent_jobs(sent_jobs)
                post_to_blogger(job)
                post_to_telegram(job)
        return

    cat = CATEGORY or fallback_category()
    job = fetch_one_job(cat)
    if not job:
        return

    sent_jobs.add(job["link"])
    save_sent_jobs(sent_jobs)
    post_to_blogger(job)
    post_to_telegram(job)

if __name__ == "__main__":
    main()
