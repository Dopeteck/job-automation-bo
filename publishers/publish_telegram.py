#!/usr/bin/env python3
"""
Telegram Publisher
- Publishes ONLY unpublished jobs
- Marks jobs as published
- Short, high-CTR format
"""

import json, os, html
from pathlib import Path
from telegram import Bot

DATA_FILE = Path("data/jobs_log.json")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL   = os.getenv("TELEGRAM_CHANNEL")

def load_jobs():
    if not DATA_FILE.exists():
        return []
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))

def save_jobs(jobs):
    DATA_FILE.write_text(json.dumps(jobs, indent=2), encoding="utf-8")

def main():
    bot = Bot(BOT_TOKEN)
    jobs = load_jobs()
    sent = 0

    for job in jobs:
        published = job.setdefault("published", {})
        if published.get("telegram"):
            continue

        msg = (
            f"🔥 <b>{html.escape(job['title'])}</b>\n"
            f"{html.escape(job['company'])}\n"
            f"Level: {job['level']}\n\n"
            f"{html.escape(job['short_desc'])}\n\n"
            f"<a href='{job['link']}'>👉 Apply Now</a>"
        )

        bot.send_message(
            chat_id=CHANNEL,
            text=msg,
            parse_mode="HTML",
            disable_web_page_preview=False
        )

        published["telegram"] = True
        sent += 1

        if sent >= 3:  # throttle per run
            break

    save_jobs(jobs)
    print(f"Telegram: published {sent} jobs")

if __name__ == "__main__":
    main()



