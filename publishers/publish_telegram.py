#!/usr/bin/env python3

import json, html, os
from pathlib import Path
from telegram import Bot

LOG_FILE = Path("data/jobs_log.json")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL   = os.getenv("TELEGRAM_CHANNEL")

def main():
    jobs = json.loads(LOG_FILE.read_text())
    bot = Bot(BOT_TOKEN)

    for job in jobs:
        if job.get["published_telegram"]:
            continue

        msg = (
            f"🔥 <b>{html.escape(job['title'])}</b>\n"
            f"{html.escape(job['company'])}\n"
            f"Level: {job['level']}\n\n"
            f"{html.escape(job['short_desc'])}\n\n"
            f"<a href='{job['link']}'>👉 Apply here</a>"
        )

        bot.send_message(chat_id=CHANNEL, text=msg, parse_mode="HTML")

        job["published_telegram"] = True
        LOG_FILE.write_text(json.dumps(jobs, indent=2))
        break  # ✅ POST ONLY ONE

if __name__ == "__main__":
    main()








