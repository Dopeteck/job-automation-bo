#!/usr/bin/env python3
"""
Publish jobs from data/jobs_log.json to Telegram
"""

import os
import json
import html
from pathlib import Path
from telegram import Bot

# =========================
# CONFIG
# =========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL")

LOG_FILE = Path("data/jobs_log.json")
POSTED_FILE = Path("data/telegram_posted.json")

POST_LIMIT = 3  # max per run

# =========================
# HELPERS
# =========================
def load_json(path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# =========================
# MAIN
# =========================
def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL:
        raise RuntimeError("Telegram credentials missing")

    jobs = load_json(LOG_FILE, [])
    posted = set(load_json(POSTED_FILE, []))

    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    sent = 0
    new_posted = []

    for job in jobs:
        if job["id"] in posted:
            continue

        text = (
            f"<b>🔥 New Job</b>\n\n"
            f"<b>{html.escape(job['title'])}</b>\n"
            f"{html.escape(job.get('company',''))}\n"
            f"Level: {job.get('level','Not specified')}\n\n"
            f"{html.escape(job.get('short_desc',''))}\n\n"
            f"<a href='{job['link']}'>👉 Apply Here</a>"
        )

        bot.send_message(
            chat_id=TELEGRAM_CHANNEL,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=False
        )

        new_posted.append(job["id"])
        sent += 1

        if sent >= POST_LIMIT:
            break

    if new_posted:
        save_json(POSTED_FILE, list(posted.union(new_posted)))

    print(f"Telegram: posted {sent} jobs")

if __name__ == "__main__":
    main()


