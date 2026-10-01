#!/usr/bin/env python3
"""Queue X posts and Substack Notes through Buffer GraphQL API."""

import json, os, re
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "editorial"
STATE = DATA / "buffer_state.json"
API = "https://api.buffer.com"
KEY = os.getenv("BUFFER_API_KEY", "").strip()
X_CHANNEL = os.getenv("BUFFER_X_CHANNEL_ID", "").strip()
SUBSTACK_CHANNEL = os.getenv("BUFFER_SUBSTACK_CHANNEL_ID", "").strip()
SAVE_AS_DRAFT = os.getenv("BUFFER_SAVE_AS_DRAFT", "true").strip().lower() != "false"
MAX_X = int(os.getenv("BUFFER_MAX_X_PER_RUN", "2"))
MAX_SUBSTACK = int(os.getenv("BUFFER_MAX_SUBSTACK_PER_RUN", "1"))

def load(path, default):
    try: return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception: return default

def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2), encoding="utf-8")

class ThreadQueueFull(RuntimeError):
    pass

def create_post(channel_id, text, thread=None):
    query = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess { post { id text dueAt } }
        ... on MutationError { message }
      }
    }
    """
    variables = {"input":{"text":text,"channelId":channel_id,"schedulingType":"automatic","mode":"addToQueue","saveToDraft":SAVE_AS_DRAFT}}
    if thread:
        if not isinstance(thread, list) or len(thread) < 2 or any(not isinstance(part, dict) or not isinstance(part.get("text"), str) or not part["text"].strip() for part in thread):
            raise ValueError("Invalid X thread; leaving item unsent.")
        variables["input"]["text"] = thread[0]["text"]
        variables["input"]["metadata"] = {"twitter": {"thread": [{"text": part["text"]} for part in thread]}}
    r = requests.post(API, headers={"Authorization":f"Bearer {KEY}","Content-Type":"application/json"}, json={"query":query,"variables":variables}, timeout=45)
    r.raise_for_status()
    body = r.json()
    if body.get("errors"): raise RuntimeError(body["errors"])
    result = body.get("data",{}).get("createPost",{})
    if result.get("message"):
        message = result["message"]
        if thread and not SAVE_AS_DRAFT and re.search(r"thread", message, re.I) and re.search(r"limit|one .*at a time|only .*one|free plan|upgrade", message, re.I):
            raise ThreadQueueFull("An X thread is already queued; try again after it publishes.")
        raise RuntimeError(message)
    post = result.get("post",{})
    if not post.get("id"):
        raise RuntimeError("Buffer did not confirm a created post; leaving item unsent.")
    return post

def publish_queue(path, key, channel_id, limit, state):
    if limit <= 0:
        return
    if not channel_id:
        print(f"Skipping {key}: no channel ID configured.")
        return
    # Revised thread drafts can be reviewed even if a legacy single post exists.
    has_threads = key == "x" and any(item.get("thread") for item in load(path, []))
    key = f"{key}_thread_draft" if SAVE_AS_DRAFT and has_threads else f"{key}_draft" if SAVE_AS_DRAFT else key
    sent = set(state.get(key, []))
    promo_key = f"{key}_promotion_weeks"
    promoted = set(state.get(promo_key, []))
    count = 0
    for item in load(path, []):
        item_id = item.get("id"); text = (item.get("text") or "").strip()
        if not item_id or not text or item_id in sent: continue
        thread = [{"text": part["text"]} for part in item.get("thread", [])] or None
        promotion_week = item.get("promotion_week")
        if promotion_week and promotion_week in promoted:
            text = "\n".join(line for line in text.splitlines() if not re.search(r"telegram|t\.me/|VettedWeb3jobs", line, re.I)).strip()
            if thread:
                for part in thread:
                    part["text"] = "\n".join(line for line in part["text"].splitlines() if not re.search(r"telegram|t\.me/|VettedWeb3jobs", line, re.I)).strip()
                text = thread[0]["text"]
            promotion_week = None
        try:
            post = create_post(channel_id, text, thread) if thread else create_post(channel_id, text)
        except ThreadQueueFull as exc:
            print(str(exc))
            return
        sent.add(item_id); state[key] = sorted(sent)
        if promotion_week:
            promoted.add(promotion_week); state[promo_key] = sorted(promoted)
        save(STATE, state)
        action = "Saved draft" if SAVE_AS_DRAFT else "Queued"
        print(f"{action} {key}: {item_id} -> {post['id']}")
        count += 1
        if count >= limit: break

def main():
    if not KEY: raise SystemExit("BUFFER_API_KEY is not configured.")
    state = load(STATE, {"x":[],"substack":[]})
    publish_queue(DATA/"x_queue.json", "x", X_CHANNEL, MAX_X, state)
    publish_queue(DATA/"substack_notes_queue.json", "substack", SUBSTACK_CHANNEL, MAX_SUBSTACK, state)

if __name__ == "__main__": main()
