#!/usr/bin/env python3
"""Queue X posts and Substack Notes through Buffer GraphQL API."""

import json, os, re, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from publishers import image_library
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
    target = Path(path)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(target)

class PublishRejected(RuntimeError):
    """Confirmed API rejection: retry on a later run is safe."""


class PublishUncertain(RuntimeError):
    """An unconfirmed mutation must not be automatically repeated."""


class ThreadQueueFull(PublishRejected):
    pass

class MediaRejected(PublishRejected):
    """Explicit media rejection, with no post created: one text retry is safe."""

def create_post(channel_id, text, thread=None, assets=None):
    query = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess { post { id text dueAt assets { id mimeType } } }
        ... on MutationError { message }
      }
    }
    """
    variables = {"input":{"text":text,"channelId":channel_id,"schedulingType":"automatic","mode":"addToQueue","saveToDraft":SAVE_AS_DRAFT}}
    if assets:
        variables["input"]["assets"] = assets
    if thread:
        if not isinstance(thread, list) or len(thread) < 2 or any(not isinstance(part, dict) or not isinstance(part.get("text"), str) or not part["text"].strip() for part in thread):
            raise ValueError("Invalid X thread; leaving item unsent.")
        variables["input"]["text"] = thread[0]["text"]
        variables["input"]["metadata"] = {"twitter": {"thread": [{"text": part["text"]} for part in thread]}}
        if assets:
            # Thread entries are the source of truth, including the root image.
            for index, part in enumerate(variables["input"]["metadata"]["twitter"]["thread"]):
                part["assets"] = assets if index == 0 else []
    try:
        r = requests.post(API, headers={"Authorization":f"Bearer {KEY}","Content-Type":"application/json"}, json={"query":query,"variables":variables}, timeout=45)
    except requests.RequestException:
        raise PublishUncertain("Buffer response not received; reconcile in Buffer before retrying.") from None
    if r.status_code in (400, 401, 403, 429):
        raise PublishRejected(f"Buffer rejected request (HTTP {r.status_code}).")
    if r.status_code >= 500:
        raise PublishUncertain(f"Buffer service error (HTTP {r.status_code}); do not blindly retry.")
    try:
        body = r.json()
    except ValueError:
        raise PublishUncertain("Buffer response was not valid JSON.") from None
    if body.get("errors"):
        raise PublishUncertain("Buffer returned GraphQL errors; check whether the post was created.")
    result = body.get("data",{}).get("createPost",{})
    if result.get("message"):
        message = result["message"]
        if thread and not SAVE_AS_DRAFT and re.search(r"thread", message, re.I) and re.search(r"limit|one .*at a time|only .*one|free plan|upgrade", message, re.I):
            raise ThreadQueueFull("An X thread is already queued; try again after it publishes.")
        if assets and re.search(r"(?:image|media|asset).*(?:invalid|unsupported|failed|unavailable|unable|cannot|could not|too large)|(?:invalid|unsupported|failed|unable|cannot|could not).*(?:image|media|asset)", message, re.I):
            raise MediaRejected("Buffer explicitly rejected the image; using text only.")
        raise PublishRejected("Buffer rejected this post; inspect the channel and its limits.")
    post = result.get("post",{})
    if not post.get("id"):
        raise PublishUncertain("Buffer did not confirm a created post; reconcile before retrying.")
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
    if SAVE_AS_DRAFT and os.getenv("EDITORIAL_IMAGE_PERCENT") == "100":
        key += "_image_review_v1"
    sent = set(state.get(key, []))
    promo_key = f"{key}_promotion_weeks"
    promoted = set(state.get(promo_key, []))
    count = 0
    pending = state.setdefault("pending_uploads", {})
    if any(record.get("channel_id") == channel_id for record in pending.values()):
        raise PublishUncertain("An earlier unconfirmed upload for this channel needs reconciliation.")
    guide_key = key + "_guides"
    guides = set(state.get(guide_key, []))
    reports = state.setdefault("last_publish_report", {})
    reports[key] = {"queued": 0, "skipped": 0, "draft": SAVE_AS_DRAFT,
                    "with_image": 0, "text_only": 0, "image_fallbacks": 0}
    latest = state.get("channel_latest_due", {}).get(channel_id)
    if not SAVE_AS_DRAFT and latest:
        try:
            if datetime.fromisoformat(latest.replace("Z", "+00:00")) > datetime.now(timezone.utc) + timedelta(hours=48):
                print(f"Holding {key}: existing queue already extends beyond 48 hours.")
                reports[key]["reason"] = "queue_horizon"
                save(STATE, state)
                return
        except (ValueError, TypeError):
            pass
    for item in load(path, []):
        item_id = item.get("id"); text = (item.get("text") or "").strip()
        if not item_id or not text or item_id in sent: continue
        pending_id = key + ":" + item_id
        if pending_id in pending:
            raise PublishUncertain("Unconfirmed earlier upload needs reconciliation; automatic retry held.")
        guide = item.get("guide_id")
        if guide and guide in guides:
            reports[key]["skipped"] += 1
            continue
        published = item.get("source_published_at")
        if published:
            try:
                age = datetime.now(timezone.utc) - datetime.fromisoformat(published.replace("Z", "+00:00"))
                if age > timedelta(hours=72) or age < -timedelta(hours=1):
                    reports[key]["skipped"] += 1
                    continue
            except (ValueError, TypeError):
                reports[key]["skipped"] += 1
                continue
        thread = [{"text": part["text"]} for part in item.get("thread", [])] or None
        promotion_week = item.get("promotion_week")
        if promotion_week and promotion_week in promoted:
            text = "\n".join(line for line in text.splitlines() if not re.search(r"telegram|t\.me/|VettedWeb3jobs", line, re.I)).strip()
            if thread:
                for part in thread:
                    part["text"] = "\n".join(line for line in part["text"].splitlines() if not re.search(r"telegram|t\.me/|VettedWeb3jobs", line, re.I)).strip()
                text = thread[0]["text"]
            promotion_week = None
        photo, media_reason = image_library.choose_image(item, key, state)
        if photo and not image_library.validate_image(photo):
            photo, media_reason = None, "image_unavailable"
            reports[key]["image_fallbacks"] += 1
        assets = image_library.buffer_assets(photo) if photo else None
        pending[pending_id] = {"channel_id": channel_id, "text": text,
                               "image_id": photo["id"] if photo else None,
                               "attempted_at": datetime.now(timezone.utc).isoformat()}
        save(STATE, state)
        try:
            if assets:
                try:
                    post = create_post(channel_id, text, thread, assets=assets)
                except MediaRejected:
                    # Only a confirmed mutation rejection permits this retry.
                    photo, assets, media_reason = None, None, "buffer_media_rejected"
                    reports[key]["image_fallbacks"] += 1
                    pending[pending_id]["image_id"] = None
                    save(STATE, state)
                    post = create_post(channel_id, text, thread) if thread else create_post(channel_id, text)
            else:
                post = create_post(channel_id, text, thread) if thread else create_post(channel_id, text)
        except PublishRejected as exc:
            pending.pop(pending_id, None)
            reports[key]["reason"] = type(exc).__name__
            save(STATE, state)
            if isinstance(exc, ThreadQueueFull):
                print(str(exc))
                return
            raise
        pending.pop(pending_id, None)
        if guide:
            guides.add(guide)
            state[guide_key] = sorted(guides)
        if post.get("dueAt"):
            state.setdefault("channel_latest_due", {})[channel_id] = post["dueAt"]
        state.setdefault("confirmed_uploads", {})[pending_id] = {
            "post_id": post["id"], "channel_id": channel_id, "due_at": post.get("dueAt"), "text": text,
            "confirmed_at": datetime.now(timezone.utc).isoformat(), "draft": SAVE_AS_DRAFT,
            "platform_key": key, "source_id": item.get("source_id"),
            "media_variant": "image" if photo else "text", "media_reason": media_reason,
            "image_id": photo["id"] if photo else None,
            "image_topic": photo["topic"] if photo else None,
            "image_source_page": photo["source_page"] if photo else None,
            "image_creator": photo["creator"] if photo else None,
            "image_license": photo["license"] if photo else None,
            "buffer_asset_ids": [asset["id"] for asset in post.get("assets", []) if asset.get("id")],
            "media_experiment": "stock-image-v1"}
        reports[key]["queued"] += 1
        reports[key]["with_image" if photo else "text_only"] += 1
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
    state["last_publish_report"] = {}
    failures = []
    for filename, platform, channel, limit in (
        ("x_queue.json", "x", X_CHANNEL, MAX_X),
        ("substack_notes_queue.json", "substack", SUBSTACK_CHANNEL, MAX_SUBSTACK)):
        try:
            publish_queue(DATA / filename, platform, channel, limit, state)
        except Exception as exc:
            # Don't let one channel failure suppress the other, or expose raw HTTP errors.
            failures.append(platform)
            print(f"::error::{platform} publishing requires attention ({type(exc).__name__}).")
    save(STATE, state)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
            summary.write("\n### Buffer delivery\n" + json.dumps(state.get("last_publish_report", {})) + "\n")
    if failures:
        raise SystemExit("Publishing needs attention: " + ", ".join(failures))

if __name__ == "__main__": main()

