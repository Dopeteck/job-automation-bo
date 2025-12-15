#!/usr/bin/env python3
import json, os, random, html
from pathlib import Path
from telegram import Bot

DATA = Path("data")
LOG_FILE = DATA / "jobs_log.json"
SENT_FILE = DATA / "telegram_sent.json"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL = os.getenv("TELEGRAM_CHANNEL")

def load_json(path, default):
    if path.exists():
        return json.loads(path.read_text())
    return default

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2))

def pick_job(jobs, sent_ids):
    # Prefer Mercor / non-RemoteOK
    preferred = [
        j for j in jobs
        if j["id"] not in sent_ids
        and j["source"].lower() != "remoteok"
    ]
    pool = preferred if preferred else [
        j for j in jobs if j["id"] not in sent_ids
    ]
    return random.choice(pool) if pool else None

def main():
    jobs = load_json(LOG_FILE, [])
    sent = set(load_json(SENT_FILE, []))

    job = pick_job(jobs, sent)
    if not job:
        print("No new Telegram job.")
        return

    msg = (
        f"🔥 <b>Remote Job</b>\n\n"
        f"<b>{html.escape(job['title'])}</b>\n"
        f"{html.escape(job['company'])}\n"
        f"Level: {job['level']}\n\n"
        f"{html.escape(job['short_desc'])}\n\n"
        f"<a href='{job['link']}'>👉 Apply here</a>"
    )

    Bot(BOT_TOKEN).send_message(
        chat_id=CHANNEL,
        text=msg,
        parse_mode="HTML",
        disable_web_page_preview=False
    )

    sent.add(job["id"])
    save_json(SENT_FILE, list(sent))
    print("Telegram post sent.")

if __name__ == "__main__":
    main()




