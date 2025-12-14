#!/usr/bin/env python3
"""
job_scraper.py — FIXED & BALANCED
"""

import os, time, pickle, html, re, random, requests
from datetime import datetime
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

import feedparser
from bs4 import BeautifulSoup

# =========================
# ENV
# =========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL   = os.getenv("TELEGRAM_CHANNEL")
BLOGGER_ID         = os.getenv("BLOGGER_ID")

CATEGORY = os.getenv("CATEGORY")
MANUAL   = os.getenv("MANUAL") == "1"
FORCE_PREPOPULATE = os.getenv("FORCE_PREPOPULATE") == "1"

REF_MERCOR  = os.getenv("REF_MERCOR")
REF_GENERIC = os.getenv("REF_GENERIC")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SENT_STORE = "sent_jobs.pkl"
TOKEN_FILE = "token_blogger.pkl"

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
        "https://cryptojobslist.com/jobs.rss",
        "https://remotive.io/remote-jobs/blockchain/feed"
    ],
    "crypto": [
        "https://crypto.jobs/rss",
        "https://cryptojobslist.com/jobs.rss",
        "https://remotive.io/remote-jobs/blockchain/feed"
    ]
}

REFERRAL_SITES = {
    "mercor.com": (REF_MERCOR, "ref"),
    "remoteok.com": (REF_GENERIC, "ref"),
    "weworkremotely.com": (REF_GENERIC, "ref"),
    "remotive.io": (REF_GENERIC, "ref")
}

ALLOWED_TAGS = ["p","br","b","strong","i","em","ul","ol","li","a","h3"]

# =========================
# STATE
# =========================
def load_sent():
    if os.path.exists(SENT_STORE):
        with open(SENT_STORE,"rb") as f:
            return pickle.load(f)
    return set()

def save_sent(s):
    with open(SENT_STORE,"wb") as f:
        pickle.dump(s,f)

sent_jobs = load_sent()

# =========================
# HELPERS
# =========================
def sanitize_html(text):
    soup = BeautifulSoup(text or "", "html.parser")
    for t in soup(["script","style"]):
        t.decompose()
    for tag in soup.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()
        else:
            tag.attrs = {}
    return str(soup)

def clean_text(text, maxlen=900):
    t = BeautifulSoup(text or "", "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+"," ",t)[:maxlen]

def detect_seniority(text):
    t = text.lower()
    if any(k in t for k in ["senior","lead","principal"]): return "Senior"
    if any(k in t for k in ["junior","entry","intern"]): return "Junior"
    if any(k in t for k in ["mid","intermediate"]): return "Mid-level"
    return "Not specified"

def apply_referral(url):
    if not url: return url
    p = urlparse(url)
    for dom,(code,param) in REFERRAL_SITES.items():
        if dom in p.netloc and code:
            q = dict(parse_qsl(p.query))
            q.setdefault(param, code)
            return urlunparse(p._replace(query=urlencode(q)))
    return url

# =========================
# AI SUMMARY
# =========================
def ai_summary(title, company, desc):
    if not OPENAI_API_KEY: return None
    try:
        import openai
        openai.api_key = OPENAI_API_KEY
        r = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":
                f"Summarize this job in 3 bullets:\n{title}\n{company}\n{desc}"
            }],
            max_tokens=120
        )
        return r.choices[0].message.content.strip()
    except:
        return None

# =========================
# MERCOR (REAL API)
# =========================
def fetch_mercor_jobs(limit=4):
    url = "https://api.mercor.com/api/jobs/public"
    try:
        r = requests.get(url,timeout=15)
        data = r.json()
    except:
        return []

    jobs = []
    for j in data.get("jobs",[])[:limit]:
        link = apply_referral(f"https://www.mercor.com/jobs/{j['slug']}")
        if link in sent_jobs: continue
        desc = j.get("description","")
        jobs.append({
            "title": j.get("title"),
            "company": "Mercor",
            "link": link,
            "html_description": sanitize_html(desc),
            "plain_description": clean_text(desc),
            "level": detect_seniority(desc),
            "ai_summary": ai_summary(j.get("title"),"Mercor",desc),
            "source": "mercor"
        })
    return jobs

# =========================
# FETCH JOB (BALANCED)
# =========================
def fetch_one_job(category):
    collected = []

    # 1️⃣ Mercor first
    collected.extend(fetch_mercor_jobs())

    # 2️⃣ RSS feeds
    for feed in FEEDS.get(category,[]):
        try:
            data = feedparser.parse(feed)
            for e in data.entries[:5]:   # cap per feed
                link = apply_referral(getattr(e,"link",None))
                if not link or link in sent_jobs: continue
                raw = getattr(e,"summary","") or getattr(e,"description","")
                plain = clean_text(raw)
                collected.append({
                    "title": getattr(e,"title","Job"),
                    "company": getattr(e,"author",""),
                    "link": link,
                    "html_description": sanitize_html(raw),
                    "plain_description": plain,
                    "level": detect_seniority(plain),
                    "ai_summary": ai_summary(getattr(e,"title",""),"",plain),
                    "source": feed
                })
        except:
            continue

    if not collected:
        return None

    # Prefer Mercor
    mercor = [j for j in collected if j["source"] == "mercor"]
    return random.choice(mercor if mercor else collected)

# =========================
# BLOGGER
# =========================
def post_to_blogger(job):
    from googleapiclient.discovery import build
    with open(TOKEN_FILE,"rb") as f:
        creds = pickle.load(f)

    service = build("blogger","v3",credentials=creds)

    body = f"""
<h3>{html.escape(job['title'])}</h3>
<p><b>Company:</b> {html.escape(job['company'])}</p>
<p><b>Level:</b> {job['level']}</p>
"""

    if job.get("ai_summary"):
        body += "<ul>" + "".join(
            f"<li>{html.escape(x)}</li>"
            for x in job["ai_summary"].splitlines()
        ) + "</ul>"

    body += f"""
{job['html_description']}
<p><a href="{job['link']}">👉 Apply Here</a></p>
"""

    service.posts().insert(
        blogId=BLOGGER_ID,
        body={"title":job["title"],"content":body},
        isDraft=False
    ).execute()

    time.sleep(8)

# =========================
# TELEGRAM
# =========================
def post_to_telegram(job):
    from telegram import Bot
    bot = Bot(TELEGRAM_BOT_TOKEN)

    msg = (
        f"<b>🔥 NEW JOB</b>\n\n"
        f"<b>{html.escape(job['title'])}</b>\n"
        f"{html.escape(job['company'])}\n"
        f"{job['level']}\n\n"
    )

    if job.get("ai_summary"):
        msg += f"{html.escape(job['ai_summary'])}\n\n"

    msg += f"<a href='{job['link']}'>👉 Apply Now</a>"

    bot.send_message(
        chat_id=TELEGRAM_CHANNEL,
        text=msg,
        parse_mode="HTML"
    )

# =========================
# PREPOPULATE
# =========================
def prepopulate(n=9):
    if sent_jobs and not FORCE_PREPOPULATE:
        return
    cats = ["tech","web3","crypto"]
    count = 0
    while count < n:
        job = fetch_one_job(cats[count % 3])
        if not job: break
        sent_jobs.add(job["link"])
        save_sent(sent_jobs)
        post_to_blogger(job)
        post_to_telegram(job)
        count += 1

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
        prepopulate()
        return

    cat = CATEGORY or fallback_category()
    job = fetch_one_job(cat)
    if not job:
        print("No job found")
        return

    sent_jobs.add(job["link"])
    save_sent(sent_jobs)
    post_to_blogger(job)
    post_to_telegram(job)

if __name__ == "__main__":
    main()
