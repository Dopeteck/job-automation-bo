#!/usr/bin/env python3

import json, os
from pathlib import Path
from telegram import Bot

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL   = os.getenv("TELEGRAM_CHANNEL")

DATA = Path("data/jobs_log.json")
SENT = Path("data/telegram_sent.json")

def load(p): return json.load(open(p)) if p.exists() else []
def save(p,d): json.dump(d, open(p,"w"), indent=2)

def main():
    bot = Bot(BOT_TOKEN)

    jobs = load(DATA)
    sent = set(load(SENT))

    new = [j for j in jobs if j["id"] not in sent]
    if not new:
        print("No Telegram jobs to post.")
        return

    for j in new[:5]:
        msg = (
            f"🔥 *New Job*\n\n"
            f"*{j['title']}*\n"
            f"{j['company']} — {j['level']}\n\n"
            f"{j['short_desc']}\n\n"
            f"[Apply here]({j['link']})"
        )
        bot.send_message(
            chat_id=CHANNEL,
            text=msg,
            parse_mode="Markdown",
            disable_web_page_preview=False
        )
        sent.add(j["id"])

    save(SENT, list(sent))
    print(f"Posted {len(new[:5])} jobs to Telegram.")

if __name__ == "__main__":
    main()
