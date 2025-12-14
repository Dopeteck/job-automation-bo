#!/usr/bin/env python3
"""
Telegram Publisher — High CTR
"""

import os, json, html
from pathlib import Path
from telegram import Bot
from openai import OpenAI

DATA_PATH = Path("data/jobs_log.json")
POSTED_PATH = Path("data/telegram_posted.json")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL   = os.getenv("TELEGRAM_CHANNEL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

def load_json(path, default):
    if path.exists():
        return json.loads(path.read_text())
    return default

def save_json(path, data):
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2))

def ai_summary(job):
    prompt = f"""
Summarize this job in 3 short bullet points.
Be concise and appealing.

Title: {job['title']}
Company: {job['company']}
Description: {job.get('short_desc','')}
"""
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}],
        max_tokens=90
    )
    return r.choices[0].message.content.strip()

def format_message(job, summary):
    bullets = "\n".join(f"• {html.escape(x)}" for x in summary.splitlines() if x.strip())
    return (
        f"🔥 <b>{html.escape(job['title'])}</b>\n"
        f"<i>{html.escape(job['company'])}</i>\n\n"
        f"{bullets}\n\n"
        f"👉 <a href='{job['link']}'>Apply here</a>"
    )

def main():
    jobs = load_json(DATA_PATH, [])
    posted = set(load_json(POSTED_PATH, []))
    bot = Bot(BOT_TOKEN)

    for job in reversed(jobs):
        if job["id"] in posted:
            continue

        summary = ai_summary(job)
        msg = format_message(job, summary)

        bot.send_message(
            chat_id=CHANNEL,
            text=msg,
            parse_mode="HTML",
            disable_web_page_preview=False
        )

        posted.add(job["id"])
        save_json(POSTED_PATH, list(posted))
        break  # ONE job per run

if __name__ == "__main__":
    main()

