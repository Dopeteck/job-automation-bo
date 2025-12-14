#!/usr/bin/env python3

import json
from datetime import datetime, timedelta

LOG_PATH = "data/jobs_log.json"
OUTPUT_MD = "digest/weekly_digest.md"

CATEGORIES = ["tech", "web3", "crypto"]

def load_recent(days=7):
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        jobs = json.load(f)

    cutoff = datetime.utcnow() - timedelta(days=days)
    return [
        j for j in jobs
        if datetime.fromisoformat(j["timestamp"].replace("Z","")) >= cutoff
    ]

def build(jobs):
    lines = []
    lines.append("# 🚀 Weekly Remote Jobs Digest\n")
    lines.append("Curated opportunities you shouldn’t miss.\n\n")

    for cat in CATEGORIES:
        cat_jobs = [j for j in jobs if j["category"] == cat][:7]
        if not cat_jobs:
            continue

        lines.append(f"## {cat.upper()} ROLES\n")
        for j in cat_jobs:
            lines.append(
                f"**{j['title']} — {j['company']}**  \n"
                f"{j['short_desc']}  \n"
                f"👉 Apply: {j['link']}\n\n"
            )

    lines.append("---\n📬 More daily jobs on Telegram")
    return "\n".join(lines)

def main():
    jobs = load_recent()
    if not jobs:
        print("No jobs for digest.")
        return

    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write(build(jobs))

    print("Weekly digest generated.")

if __name__ == "__main__":
    main()
