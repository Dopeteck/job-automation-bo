#!/usr/bin/env python3

import json, os, html
from pathlib import Path
from telegram import Bot

LOG_FILE = Path("data/jobs_log.json")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL = os.getenv("TELEGRAM_CHANNEL")

def load_jobs():
    return json.loads(LOG_FILE.read_text())

def save_jobs(jobs):
    LOG_FILE.write_text(json.dumps(jobs, indent=2))

def main():
    bot = Bot(BOT_TOKEN)
    jobs = load_jobs()

    for job in jobs:
        pub = job.setdefault("published", {})
        if pub.get("telegram"):
            continue

        msg = (
            f"<b>{html.escape(job['title'])}</b>\n"
            f"{html.escape(job['company'])}\n"
            f"{job['level']} • {job['category'].upper()}\n\n"
            f"{html.escape(job['short_desc'])}\n\n"
            f"<a href='{job['link']}'>👉 Apply here</a>"
        )

        bot.send_message(
            chat_id=CHANNEL,
            text=msg,
            parse_mode="HTML",
            disable_web_page_preview=False
        )

        job["published"]["telegram"] = True
        save_jobs(jobs)
        print("Posted ONE job to Telegram")
        return

    print("No unpublished jobs for Telegram")

if __name__ == "__main__":
    main()







