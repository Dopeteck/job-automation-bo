#!/usr/bin/env python3
"""Queue X posts and Substack Notes through Buffer GraphQL API."""

import json, os
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

def create_post(channel_id, text):
    query = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess { post { id text dueAt } }
        ... on MutationError { message }
      }
    }
    """
    variables = {"input":{"text":text,"channelId":channel_id,"schedulingType":"automatic","mode":"addToQueue","saveToDraft":SAVE_AS_DRAFT}}
    r = requests.post(API, headers={"Authorization":f"Bearer {KEY}","Content-Type":"application/json"}, json={"query":query,"variables":variables}, timeout=45)
    r.raise_for_status()
    body = r.json()
    if body.get("errors"): raise RuntimeError(body["errors"])
    result = body.get("data",{}).get("createPost",{})
    if result.get("message"): raise RuntimeError(result["message"])
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
    key = f"{key}_draft" if SAVE_AS_DRAFT else key
    sent = set(state.get(key, []))
    count = 0
    for item in load(path, []):
        item_id = item.get("id"); text = (item.get("text") or "").strip()
        if not item_id or not text or item_id in sent: continue
        post = create_post(channel_id, text)
        sent.add(item_id); state[key] = sorted(sent); save(STATE, state)
        print(f"Queued {key}: {item_id} -> {post.get('id','unknown')}")
        count += 1
        if count >= limit: break

def main():
    if not KEY: raise SystemExit("BUFFER_API_KEY is not configured.")
    state = load(STATE, {"x":[],"substack":[]})
    publish_queue(DATA/"x_queue.json", "x", X_CHANNEL, MAX_X, state)
    publish_queue(DATA/"substack_notes_queue.json", "substack", SUBSTACK_CHANNEL, MAX_SUBSTACK, state)

if __name__ == "__main__": main()
