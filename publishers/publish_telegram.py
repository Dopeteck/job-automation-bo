#!/usr/bin/env python3

import json, os, html
from pathlib import Path
from telegram import Bot

DATA = Path("data")
LOG_FILE = DATA / "jobs_log.json"
SENT_FILE = DATA / "sent_telegram.json"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL   = os.getenv("TELEGRAM_CHANNEL")

DATA.mkdir(exist_ok=True)

def load_json(path, default):
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        return json.loads(path.read_text())
    except:
        return default

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2))

def main():
    jobs = load_json(LOG_FILE, [])
    sent = set(load_json(SENT_FILE, []))

    # find ONE unsent job
    job = next((j for j in jobs if j["id"] not in sent), None)

    if not job:
        print("No new Telegram jobs.")
        return

    bot = Bot(BOT_TOKEN)

    msg = (
        f"<b>🚀 Remote Job</b>\n\n"
        f"<b>{html.escape(job['title'])}</b>\n"
        f"{html.escape(job['company'])}\n"
        f"{job['level']}\n\n"
        f"{html.escape(job['short_desc'])}\n\n"
        f"<a href='{job['link']}'>👉 Apply Here</a>"
    )

    bot.send_message(chat_id=CHANNEL, text=msg, parse_mode="HTML")

    sent.add(job["id"])
    save_json(SENT_FILE, list(sent))
    print("Telegram post sent.")

if __name__ == "__main__":
    main()






