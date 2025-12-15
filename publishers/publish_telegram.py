#!/usr/bin/env python3

import json, os
from pathlib import Path
from telegram import Bot

DATA_FILE = Path("data/jobs_log.json")
SENT_FILE = Path("data/sent_telegram.json")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL   = os.getenv("TELEGRAM_CHANNEL")

def load_json_safe(path, default):
    try:
        if not path.exists():
            return default
        text = path.read_text().strip()
        if not text:
            return default
        return json.loads(text)
    except Exception:
        return default

def save_json(path, data):
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2))

def main():
    jobs = load_json_safe(DATA_FILE, [])
    sent = set(load_json_safe(SENT_FILE, []))

    # 🔴 pick ONE unsent job only
    job = next((j for j in jobs if j["id"] not in sent), None)
    if not job:
        print("No new Telegram jobs.")
        return

    bot = Bot(BOT_TOKEN)

    msg = (
        f"🔥 <b>{job['title']}</b>\n\n"
        f"🏢 {job['company']}\n"
        f"📌 {job['level']}\n\n"
        f"{job['short_desc']}\n\n"
        f"<a href='{job['link']}'>👉 Apply here</a>"
    )

    bot.send_message(
        chat_id=CHANNEL,
        text=msg,
        parse_mode="HTML",
        disable_web_page_preview=False
    )

    sent.add(job["id"])
    save_json(SENT_FILE, list(sent))

    print("Telegram posted:", job["title"])

if __name__ == "__main__":
    main()





