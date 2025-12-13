#!/usr/bin/env python3
"""
job_scraper.py

One-shot job scraper & publisher (updated with Mercor + referral support)
- ENV:
    TELEGRAM_BOT_TOKEN   (required)
    TELEGRAM_CHANNEL     (required, e.g. @VettedWeb3jobs)
    BLOGGER_ID           (required)
    CATEGORY             (optional) one of: tech, web3, crypto
    MANUAL               set to "1" for manual run (prepopulate 9 + post one per category)
    FORCE_PREPOPULATE    set to "1" to force sending starter posts even if sent_jobs exists
    REF_MERCOR           (optional) your Mercor referral code
    REF_GENERIC          (optional) fallback referral code for some boards
- Requires token_blogger.pkl (uploaded to Actions) for Blogger posting
- Uses python-telegram-bot==13.7 (sync)
"""

import os
import time
import pickle
import html
import re
from datetime import datetime
from bs4 import BeautifulSoup
import feedparser
import traceback
import requests
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

# ---------------------------
# ENV / CONFIG
# ---------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL")
BLOGGER_ID = os.getenv("BLOGGER_ID")
CATEGORY = os.getenv("CATEGORY")  # "tech" / "web3" / "crypto"
MANUAL = os.getenv("MANUAL", "0") == "1"
FORCE_PREPOPULATE = os.getenv("FORCE_PREPOPULATE", "0") == "1"

# Referral codes (set as envs / GitHub secrets)
REF_MERCOR = os.getenv("REF_MERCOR")    # e.g. "MYMERCORCODE"
REF_GENERIC = os.getenv("REF_GENERIC")  # fallback

SENT_STORE = "sent_jobs.pkl"
TOKEN_FILE = "token_blogger.pkl"

# Feeds (added WeWorkRemotely; Mercor handled specially)
FEEDS = {
    "tech": [
        "https://remoteok.com/remote-jobs.rss",
        "https://stackoverflow.com/jobs/feed",
        "https://weworkremotely.com/remote-jobs.rss"
    ],
    "web3": [
        "https://web3.career/rss",
        "https://thirdweb.com/careers/rss"
    ],
    "crypto": [
        "https://crypto.jobs/rss",
        "https://cryptojobslist.com/jobs.rss"
    ],
    # special "mercor" feed handled by HTML scraping
    "mercor": [
        "https://www.mercor.com/careers",   # example (adjust if Mercor careers URL differs)
        "https://work.mercor.com/"
    ]
}

ALLOWED_TAGS = ["p", "br", "b", "strong", "i", "em", "ul", "ol", "li", "a", "h1", "h2", "h3"]

# Referral mapping: domain -> (ref_code_env_var_value, param_name)
REFERRAL_SITES = {
    "mercor.com": (REF_MERCOR, "ref"),
    "work.mercor.com": (REF_MERCOR, "ref"),
    "remoteok.com": (REF_GENERIC, "ref"),
    "weworkremotely.com": (REF_GENERIC, "ref")
}

# ---------------------------
# Utilities
# ---------------------------
def load_sent_jobs():
    try:
        if os.path.exists(SENT_STORE):
            with open(SENT_STORE, "rb") as f:
                return pickle.load(f)
    except Exception:
        print("Warning: failed to load sent_jobs.pkl (will recreate).")
    return set()

def save_sent_jobs(s):
    with open(SENT_STORE, "wb") as f:
        pickle.dump(s, f)

sent_jobs = load_sent_jobs()

def sanitize_html_keep_basic(html_text):
    soup = BeautifulSoup(html_text or "", "html.parser")
    for bad in soup(["script", "style"]):
        bad.decompose()
    for tag in soup.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()
        else:
            if tag.name == "a":
                href = tag.get("href")
                tag.attrs = {}
                if href and isinstance(href, str) and href.startswith("http"):
                    tag.attrs["href"] = href
                else:
                    tag.unwrap()
            else:
                tag.attrs = {}
    text = str(soup)
    text = re.sub(r'\n\s*\n', '\n', text)
    return text.strip()

def clean_text_plain(html_text, maxlen=600):
    s = BeautifulSoup(html_text or "", "html.parser").get_text(separator=" ", strip=True)
    s = re.sub(r'\s+', ' ', s)
    return s[:maxlen] + ("..." if len(s) > maxlen else "")

def detect_seniority(text):
    if not text:
        return "Not specified"
    t = text.lower()
    senior_keys = ["senior", "lead", "principal", "manager", "5+ years", "5 years"]
    mid_keys = ["mid", "intermediate", "2 years", "3 years", "4 years", "2+ years"]
    junior_keys = ["junior", "entry", "entry-level", "intern", "graduate"]
    if any(k in t for k in senior_keys):
        return "Senior"
    if any(k in t for k in mid_keys):
        return "Mid-level"
    if any(k in t for k in junior_keys):
        return "Junior"
    return "Not specified"

# ---------------------------
# Referral helper
# ---------------------------
def apply_referral(url, site_key=None):
    """Append referral parameter to url when a code exists for that site."""
    if not url:
        return url
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    # determine param name & code
    ref_code = None
    param_name = "ref"
    # explicit site_key first
    if site_key and site_key in REFERRAL_SITES and REFERRAL_SITES[site_key][0]:
        ref_code, param_name = REFERRAL_SITES[site_key]
    else:
        # match domain substrings
        for dom, (code, pname) in REFERRAL_SITES.items():
            if dom in domain and code:
                ref_code, param_name = (code, pname)
                break
        if not ref_code:
            ref_code = REF_GENERIC

    if not ref_code:
        return url

    # preserve existing query params, avoid duplication
    q = dict(parse_qsl(parsed.query))
    if param_name in q:
        return url
    q[param_name] = ref_code
    new_query = urlencode(q)
    new_parsed = parsed._replace(query=new_query)
    return urlunparse(new_parsed)

# ---------------------------
# Blogger
# ---------------------------
def get_blogger_service():
    try:
        from googleapiclient.discovery import build
    except Exception as e:
        raise RuntimeError("Missing googleapiclient library. Install requirements.") from e
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)
    else:
        raise RuntimeError(f"{TOKEN_FILE} not found. Create it locally and upload as secret for Actions.")
    service = build("blogger", "v3", credentials=creds)
    return service

def post_to_blogger(job):
    try:
        service = get_blogger_service()
        content_html = f"""
<h2>{html.escape(job.get('title',''))}</h2>
<p><b>Company:</b> {html.escape(job.get('company',''))}</p>
<p><b>Seniority:</b> {html.escape(job.get('level','Not specified'))}</p>
<hr/>
{job.get('html_description','')}
<p><b>Apply:</b> <a href="{html.escape(job.get('link',''))}">{html.escape(job.get('link',''))}</a></p>
"""
        body = {
            "kind": "blogger#post",
            "blog": {"id": BLOGGER_ID},
            "title": job.get("title","Job"),
            "content": content_html
        }
        resp = service.posts().insert(blogId=BLOGGER_ID, body=body, isDraft=False).execute()
        print("[Blogger] Posted:", job.get("title"), "->", resp.get("url"))
        time.sleep(10)
    except Exception as e:
        print("[Blogger] Error posting:", e)
        traceback.print_exc()

# ---------------------------
# Telegram (sync-safe)
# ---------------------------
def post_to_telegram(job):
    try:
        from telegram import Bot
        from telegram.parsemode import ParseMode
    except Exception as e:
        print("Telegram library missing or wrong version. Install python-telegram-bot==13.7")
        raise

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    desc_html = job.get("html_description", "") or ""
    desc_text = BeautifulSoup(desc_html, "html.parser").get_text(separator="\n", strip=True)
    desc_text = re.sub(r'\n\s*\n+', '\n\n', desc_text).strip()
    if len(desc_text) > 3000:
        desc_text = desc_text[:3000] + "..."

    title = html.escape(job.get("title",""))
    company = html.escape(job.get("company",""))
    level = html.escape(job.get("level","Not specified"))
    apply_link = html.escape(job.get("link",""))

    body_text = (
        f"<b>🔥 NEW JOB</b>\n\n"
        f"<b>Role:</b> {title}\n"
        f"<b>Company:</b> {company}\n"
        f"<b>Seniority:</b> {level}\n\n"
        f"{html.escape(desc_text)}\n\n"
        f"<b>Apply:</b> <a href=\"{apply_link}\">Apply Here</a>"
    )

    try:
        bot.send_message(
            chat_id=TELEGRAM_CHANNEL,
            text=body_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False
        )
        print(f"[Telegram] Posted: {job.get('title')}")
    except Exception as e:
        print("[Telegram] Error posting:", e)
        traceback.print_exc()

# ---------------------------
# Fetch job (RSS + Mercor HTML scraping)
# ---------------------------
def fetch_one_job_for_category(category):
    feeds = FEEDS.get(category, [])
    for feed in feeds:
        try:
            # Mercor HTML scraping special-case
            if "mercor" in feed or "work.mercor" in feed:
                try:
                    resp = requests.get(feed, timeout=15, headers={"User-Agent":"jobbot/1.0"})
                    if resp.status_code != 200:
                        continue
                    soup = BeautifulSoup(resp.text, "html.parser")
                    candidates = []
                    # look for anchors likely to be job links
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "/job" in href.lower() or "/jobs" in href.lower() or "career" in href.lower():
                            full = href if href.startswith("http") else requests.compat.urljoin(feed, href)
                            title_text = a.get_text(strip=True) or None
                            candidates.append((full, title_text))
                    seen_links = set()
                    for link, title_text in candidates:
                        if not link or link in sent_jobs or link in seen_links:
                            continue
                        seen_links.add(link)
                        # optional fetch job page for description
                        desc_html = ""
                        try:
                            r2 = requests.get(link, timeout=10, headers={"User-Agent":"jobbot/1.0"})
                            if r2.status_code == 200:
                                page_soup = BeautifulSoup(r2.text, "html.parser")
                                desc_el = page_soup.find(class_="description") or page_soup.find(class_="job-description") or page_soup.find("article") or page_soup.find("div", {"id":"job-description"})
                                desc_html = str(desc_el) if desc_el else ""
                        except Exception:
                            desc_html = ""
                        job = {
                            "title": title_text or "Job at Mercor",
                            "company": "Mercor",
                            "link": apply_referral(link, "mercor.com"),
                            "html_description": sanitize_html_keep_basic(desc_html),
                            "plain_description": clean_text_plain(desc_html)
                        }
                        job["level"] = detect_seniority(job["plain_description"])
                        return job
                    continue
                except Exception as e:
                    print("[Fetch] Mercor scraping error:", e)
                    traceback.print_exc()
                    continue

            # Default RSS flow
            data = feedparser.parse(feed)
            if not data or not getattr(data, "entries", None):
                continue
            for entry in data.entries:
                link = getattr(entry, "link", None)
                if not link:
                    continue
                if link in sent_jobs:
                    continue
                raw_desc = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
                html_desc = sanitize_html_keep_basic(raw_desc)
                plain = clean_text_plain(raw_desc, maxlen=1200)
                link_with_ref = apply_referral(link)
                job = {
                    "title": getattr(entry, "title", "No title"),
                    "company": getattr(entry, "author", "") or getattr(entry, "company", "") or "",
                    "link": link_with_ref,
                    "html_description": html_desc,
                    "plain_description": plain
                }
                job['level'] = detect_seniority(job['plain_description'])
                return job
        except Exception as e:
            print(f"[Fetch] Error fetching from {feed}: {e}")
            traceback.print_exc()
            continue
    return None

# ---------------------------
# Prepopulate (manual)
# ---------------------------
def prepopulate_first_n(n=9):
    if len(sent_jobs) > 0 and not FORCE_PREPOPULATE:
        print("[Prepopulate] Already populated. Skipping.")
        return
    if FORCE_PREPOPULATE:
        print("[Prepopulate] FORCE enabled - will send starter posts even if sent_jobs exists.")
    print("[Prepopulate] Sending initial posts...")
    count = 0
    cats = ["tech","web3","crypto"]
    i = 0
    # rotate through categories to get a balanced starter set
    while count < n and i < n * 6:
        cat = cats[i % len(cats)]
        job = fetch_one_job_for_category(cat)
        if job:
            try:
                sent_jobs.add(job["link"])
                save_sent_jobs(sent_jobs)
                post_to_blogger(job)
                post_to_telegram(job)
                count += 1
                time.sleep(1)
            except Exception as e:
                print("[Prepopulate] Error posting job:", e)
                traceback.print_exc()
        i += 1
    print(f"[Prepopulate] Done. Sent {count} starter posts.")

# ---------------------------
# Main & fallback mapping
# ---------------------------
def fallback_category_from_utc():
    hour = datetime.utcnow().hour
    if hour == 12:
        return "tech"
    if hour == 16:
        return "web3"
    if hour == 20:
        return "crypto"
    if 11 <= hour <= 13:
        return "tech"
    if 15 <= hour <= 17:
        return "web3"
    if 19 <= hour <= 21:
        return "crypto"
    return "tech"

def main():
    print("job_scraper.py start - MANUAL =", MANUAL, "CATEGORY env =", CATEGORY, "FORCE_PREPOPULATE =", FORCE_PREPOPULATE)
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL or not BLOGGER_ID:
        print("ERROR: TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL, and BLOGGER_ID must be set in environment.")
        return

    if MANUAL:
        try:
            prepopulate_first_n(9)
        except Exception as e:
            print("Prepopulate error:", e)
            traceback.print_exc()
        # post one for each category immediately
        for cat in ["tech","web3","crypto"]:
            print("Manual posting for category:", cat)
            job = fetch_one_job_for_category(cat)
            if job:
                sent_jobs.add(job["link"])
                save_sent_jobs(sent_jobs)
                try:
                    post_to_blogger(job)
                except Exception as e:
                    print("Blogger post error:", e)
                try:
                    post_to_telegram(job)
                except Exception as e:
                    print("Telegram post error:", e)
            else:
                print("No job found for", cat)
        print("Manual run finished.")
        return

    run_cat = CATEGORY or fallback_category_from_utc()
    print("Scheduled run - category:", run_cat)
    job = fetch_one_job_for_category(run_cat)
    if not job:
        print("No new", run_cat, "job found.")
        return

    sent_jobs.add(job["link"])
    save_sent_jobs(sent_jobs)

    try:
        post_to_blogger(job)
    except Exception as e:
        print("Blogger post error:", e)
        traceback.print_exc()

    try:
        post_to_telegram(job)
    except Exception as e:
        print("Telegram post error:", e)
        traceback.print_exc()

    print("Scheduled run finished.")

if __name__ == "__main__":
    main()
