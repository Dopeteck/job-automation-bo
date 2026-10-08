"""Optional, reviewed stock photos. No image search API or AI calls at runtime."""

import hashlib
import io
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image

LIBRARY = Path(__file__).with_name("image_library.json")
MAX_BYTES = 4_000_000  # Below both X and Substack limits.
TOPICS = {
    "coding": r"\b(code|coding|programming|developer|github|readme|debug|software)\b",
    "workflow": r"\b(faq|bot|chatbot|automation|workflow|agent|agents|handoff)\b",
    "remote": r"\b(remote|worldwide|time.zone|working hours|contract type)\b",
    "interview": r"\b(interview|resume|recruit|vacancies|application|hiring|salary)\b",
    "infrastructure": r"\b(server|cloud|network|cybersecurity|security|vulnerability|secrets)\b",
    "hardware": r"\b(chip|processor|gpu|cpu|semiconductor|hardware)\b",
}


def read_library():
    try:
        value = json.loads(LIBRARY.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, ValueError):
        return []


def safe_url(url):
    parsed = urlparse(url or "")
    return (parsed.scheme == "https" and parsed.hostname == "images.pexels.com"
            and parsed.port in (None, 443) and not parsed.username
            and not parsed.password and parsed.path.startswith("/photos/"))


def approved_photo(photo):
    try:
        return (photo.get("approved") is True and photo.get("kind") == "stock_illustration"
                and photo.get("license") == "Pexels License" and safe_url(photo.get("url"))
                and photo.get("creator") and photo.get("source_page")
                and photo.get("alt") and photo.get("id") and photo.get("topic") in TOPICS)
    except (ValueError, AttributeError):
        return False


def choose_image(item, key, state):
    """Stable source-level experiment assignment; no claims of causal uplift."""
    try:
        percent = max(0, min(100, int(os.getenv("EDITORIAL_IMAGE_PERCENT", "50"))))
    except ValueError:
        percent = 50
    identity = str(item.get("source_id") or item.get("id", ""))
    bucket = int(hashlib.sha256(identity.encode()).hexdigest()[:8], 16) % 100
    if bucket >= percent:
        return None, "text_control"
    text = " ".join(part.get("text", "") for part in item.get("thread", [])) or item.get("text", "")
    scores = {topic: len(re.findall(pattern, text, re.I)) for topic, pattern in TOPICS.items()}
    topics = sorted((t for t in TOPICS if scores[t]), key=lambda t: scores[t], reverse=True)
    if not topics:
        return None, "no_topic_match"
    recent = set()
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    for upload in state.get("confirmed_uploads", {}).values():
        if upload.get("platform_key") != key or not upload.get("image_id"):
            continue
        try:
            timestamp = datetime.fromisoformat(upload["confirmed_at"].replace("Z", "+00:00"))
            if timestamp >= cutoff:
                recent.add(upload["image_id"])
        except (ValueError, TypeError, KeyError):
            recent.add(upload["image_id"])
    negative_context = re.search(r"\b(scam|fraud|fake|dishonest|criminal|fired)\b", text, re.I)
    photos = read_library()
    for topic in topics:
        matches = [p for p in photos if approved_photo(p) and p["topic"] == topic
                   and p["id"] not in recent
                   and not (negative_context and p.get("identifiable_people"))]
        matches.sort(key=lambda p: hashlib.sha256((identity + p["id"]).encode()).hexdigest())
        if matches:
            return matches[0], "image_candidate"
    return None, "no_unused_match"


def validate_image(photo):
    """Bounded download and decode, with redirects disabled. Failure is optional."""
    if not approved_photo(photo):
        return False
    try:
        with requests.get(photo["url"], timeout=(5, 15), stream=True,
                          allow_redirects=False) as response:
            if response.status_code != 200:
                return False
            if response.headers.get("Content-Type", "").split(";")[0].lower() not in ("image/jpeg", "image/png"):
                return False
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_BYTES:
                return False
            data = bytearray()
            for chunk in response.iter_content(64 * 1024):
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    return False
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ("JPEG", "PNG") or image.width < 800 or image.height < 400:
                return False
            if image.width * image.height > 20_000_000:
                return False
            image.verify()
        return True
    except (requests.RequestException, OSError, ValueError, Image.DecompressionBombError):
        return False


def buffer_assets(photo):
    # Keep licensing evidence internally; these stock photos don't require links
    # in the published text. Alt text identifies them as illustrative imagery.
    return [{"image": {"url": photo["url"], "metadata": {
        "altText": "Illustrative stock photo: " + photo["alt"]}}}]
