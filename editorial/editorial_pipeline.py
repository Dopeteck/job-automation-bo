#!/usr/bin/env python3
"""Build tech/career newsletter, X, and Substack Note drafts from fresh RSS + jobs."""

from __future__ import annotations
import hashlib, json, os, re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "editorial"
OUT.mkdir(parents=True, exist_ok=True)
SOURCES = Path(__file__).with_name("sources.json")
JOBS = ROOT / "data" / "jobs_log.json"

PUBLICATION = os.getenv("PUBLICATION_NAME", "Web3 Job Tech Alpha Vault").strip() or "Web3 Job Tech Alpha Vault"
TELEGRAM_URL = os.getenv("TELEGRAM_URL", "https://t.me/VettedWeb3jobs").strip()
X_HANDLE = os.getenv("X_HANDLE", "@HenryMortu").strip()
SUBSTACK_URL = os.getenv("SUBSTACK_URL", "https://substack.com/@web3jobtechalphavault").strip()
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()

CAREER_TERMS = {
    "job":4,"jobs":4,"career":5,"hiring":6,"hire":4,"layoff":5,"skills":5,
    "developer":3,"engineering":3,"remote":5,"salary":5,"interview":5,
    "resume":5,"recruit":4,"freelance":4,"certification":4,"learning":3,
    "training":3,"ai":3,"artificial intelligence":4,"automation":3,
    "github":2,"coding":3,"programming":3,"cybersecurity":3,"data":2
}

def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default

def clean(value, limit=700):
    text = BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()[:limit]

def item_id(source, title, link):
    return hashlib.sha256(f"{source}|{title}|{link}".lower().encode()).hexdigest()[:20]

def entry_time(entry):
    for key in ("published_parsed", "updated_parsed"):
        value = getattr(entry, key, None)
        if value:
            return datetime(*value[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)

def score(title, summary, priority, published):
    text = f"{title} {summary}".lower()
    total = int(priority) * 3
    for term, weight in CAREER_TERMS.items():
        if term in text:
            total += weight
    age_h = max(0, (datetime.now(timezone.utc)-published).total_seconds()/3600)
    total += 8 if age_h <= 24 else 5 if age_h <= 48 else 2 if age_h <= 96 else 0
    return total

def collect_news():
    cutoff = datetime.now(timezone.utc) - timedelta(days=4)
    items = []
    for src in load_json(SOURCES, []):
        feed = feedparser.parse(src["url"])
        for e in feed.entries[:12]:
            title = clean(getattr(e, "title", ""), 220)
            link = getattr(e, "link", "")
            summary = clean(getattr(e, "summary", "") or getattr(e, "description", ""))
            if not title or not link:
                continue
            published = entry_time(e)
            if published < cutoff:
                continue
            items.append({
                "id": item_id(src["name"], title, link),
                "source": src["name"], "domain": urlparse(link).netloc,
                "category": src.get("category","tech"), "title": title,
                "summary": summary, "link": link, "published_at": published.isoformat(),
                "score": score(title, summary, src.get("priority",3), published)
            })
    unique = {x["id"]: x for x in items}
    return sorted(unique.values(), key=lambda x:x["score"], reverse=True)[:6]

def select_jobs():
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    out = []
    for j in reversed(load_json(JOBS, [])):
        try:
            ts = datetime.fromisoformat(j.get("timestamp","").replace("Z","+00:00"))
            if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if ts < cutoff: continue
        text = f"{j.get('title','')} {j.get('short_desc','')}".lower()
        s = (5 if any(x in text for x in ("ai","llm","machine learning")) else 0)
        s += 4 if any(x in text for x in ("entry","junior","intern","trainee")) else 0
        s += 4 if any(x in text for x in ("remote","worldwide","global")) else 0
        s += 2 if j.get("category") in ("web3","crypto") else 0
        out.append({
            "id":j.get("id"),"title":j.get("title",""),"company":j.get("company",""),
            "level":j.get("level","Not specified"),"summary":j.get("short_desc",""),
            "link":j.get("link",""),"score":s
        })
    return sorted(out, key=lambda x:x["score"], reverse=True)[:5]

def cta():
    return f"Get real-time job alerts on Telegram: {TELEGRAM_URL}" if TELEGRAM_URL else "Get real-time job alerts on our Telegram channel."

def fallback(news, jobs):
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    md = [f"# {PUBLICATION} — {today}","", "AI, tech, careers and opportunities worth paying attention to.","","## What changed",""]
    for n in news[:4]:
        md += [f"### {n['title']}", n["summary"] or "A development worth watching.", f"Source: {n['source']} — {n['link']}",""]
    md += ["## Career move of the week","", "Choose one role you want, identify the three repeated skills in its requirements, and build one small proof-of-work project around one of them.","","## Opportunities",""]
    for j in jobs:
        md.append(f"- **{j['title']} — {j['company']}** ({j['level']}) — {j['link']}")
    md += ["","---",cta(), f"Follow on X: {X_HANDLE}", f"Read/subscribe on Substack: {SUBSTACK_URL}", ""]
    xq=[]; nq=[]
    for n in news[:5]:
        xq.append({"id":"x-"+n["id"],"source_id":n["id"],"text":(n["title"]+"\n\nWhy it matters for tech careers: "+n["summary"][:170]+"\n\n"+n["link"])[:275]})
        nq.append({"id":"note-"+n["id"],"source_id":n["id"],"text":n["title"]+"\n\n"+n["summary"]+"\n\nCareer angle: watch how this changes the skills, tools or hiring expectations people need to pay attention to.\n\n"+n["link"]})
    return {"newsletter_markdown":"\n".join(md),"x_posts":xq,"substack_notes":nq}

def ai_outputs(news, jobs):
    if not GEMINI_KEY: return None
    packet = {"publication_name":PUBLICATION,"telegram_cta":cta(),"x_handle":X_HANDLE,"substack_url":SUBSTACK_URL,"news":news,"jobs":jobs}
    prompt = """You are the editor of a practical tech-career publication. Using ONLY the supplied source packet, return JSON with newsletter_markdown, x_posts, and substack_notes. Focus on AI/tech developments that affect careers, concrete career advice, useful tools/skills, and a few strong jobs. Do not invent facts. Include source URLs for factual news. X posts must be useful standalone insights, not link spam. Substack Notes may be conversational. Newsletter structure: opening; 3-5 developments; what it means for careers; one practical move; 3-5 jobs; Telegram CTA.\n\nSOURCE PACKET:\n""" + json.dumps(packet, ensure_ascii=False)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
    payload = {"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.35,"responseMimeType":"application/json"}}
    r = requests.post(url, json=payload, timeout=90); r.raise_for_status()
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    return json.loads(text)

def main():
    news, jobs = collect_news(), select_jobs()
    if not news and not jobs: raise SystemExit("No fresh editorial material found.")
    outputs = None
    if GEMINI_KEY:
        try: outputs = ai_outputs(news, jobs)
        except Exception as exc: print(f"AI generation failed; using fallback: {exc}")
    if not outputs: outputs = fallback(news, jobs)
    (OUT/"latest_items.json").write_text(json.dumps({"news":news,"jobs":jobs},indent=2,ensure_ascii=False),encoding="utf-8")
    (OUT/"latest_digest.md").write_text(outputs["newsletter_markdown"].strip()+"\n",encoding="utf-8")
    (OUT/"x_queue.json").write_text(json.dumps(outputs.get("x_posts",[]),indent=2,ensure_ascii=False),encoding="utf-8")
    (OUT/"substack_notes_queue.json").write_text(json.dumps(outputs.get("substack_notes",[]),indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"Saved {len(news)} news stories and {len(jobs)} jobs.")

if __name__ == "__main__": main()
