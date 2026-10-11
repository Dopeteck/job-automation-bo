from __future__ import annotations

import re
from datetime import datetime, timezone

from .config import Settings
from .classify import is_automation
from .language import is_probably_english
from .models import Job


BLOCK_TERMS = {
    "bootcamp",
    "course enrollment",
    "pay to apply",
    "paid training course",
    "job guaranteed",
    "volunteer ambassador",
    "unpaid internship",
    "commission only",
}

GENERIC_TITLES = {
    "job",
    "remote job",
    "work from home",
    "remote opportunity",
    "multiple positions",
    "various roles",
}

NON_VACANCY_TITLES = {
    "initiative application", "spontaneous application", "speculative application",
    "talent pool", "talent network", "trainers network", "future opportunities",
}


def age_days(job: Job, now: datetime | None = None) -> float | None:
    if not job.published_at:
        return None
    now = now or datetime.now(timezone.utc)
    published = job.published_at
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return max(0.0, (now - published).total_seconds() / 86400)


def score_job(job: Job, settings: Settings, now: datetime | None = None) -> Job:
    score = 0
    reasons: list[str] = []
    text = " ".join([job.title, job.company, job.description]).lower()

    if not job.title.strip() or job.title.strip().lower() in GENERIC_TITLES:
        job.quality_score = -100
        job.quality_reasons = ["rejected: generic or missing title"]
        return job
    if any(term in job.title.lower() for term in NON_VACANCY_TITLES):
        job.quality_score = -100
        job.quality_reasons = ["rejected: talent pool or speculative application, not a specific vacancy"]
        return job
    if any(term in text for term in BLOCK_TERMS):
        job.quality_score = -100
        job.quality_reasons = ["rejected: course, unpaid, or promotional listing"]
        return job
    if not is_probably_english(" ".join([job.title, job.description])):
        job.quality_score = -100
        job.quality_reasons = ["rejected: non-English listing"]
        return job
    if (
        job.remote_scope != "unknown"
        and job.remote_scope not in settings.allowed_remote_scopes
    ):
        job.quality_score = -100
        job.quality_reasons = [f"rejected: outside target region ({job.remote_scope})"]
        return job
    if job.link_status in {"404", "410", "invalid"}:
        job.quality_score = -100
        job.quality_reasons = ["rejected: broken application link"]
        return job

    age = age_days(job, now)
    if age is not None and age > settings.max_job_age_days:
        job.quality_score = -100
        job.quality_reasons = [f"rejected: {age:.1f} days old"]
        return job
    if age is None:
        score -= 1
        reasons.append("publication date unavailable (-1)")
    elif age <= 1:
        score += 5
        reasons.append("posted within 24h (+5)")
    elif age <= 3:
        score += 4
        reasons.append("posted within 3 days (+4)")
    elif age <= 7:
        score += 2
        reasons.append("posted within 7 days (+2)")

    if job.remote_scope == "worldwide":
        score += 4
        reasons.append("worldwide (+4)")
    else:
        score += 1
        reasons.append("remote scope accepted (+1)")

    if job.salary:
        score += 2
        reasons.append("salary disclosed (+2)")
    if job.category == "ai":
        score += 2
        reasons.append("AI opportunity (+2)")
    if is_automation(job):
        score += 2
        reasons.append("automation work (+2)")
    if job.experience_level == "entry":
        score += 3
        reasons.append("entry level (+3)")
    elif job.experience_level == "senior":
        score -= 1
        reasons.append("senior role (-1)")
    if job.company and job.company.lower() not in {"unknown", "remote company", "confidential"}:
        score += 1
        reasons.append("identified employer (+1)")
    else:
        score -= 3
        reasons.append("unclear employer (-3)")
    if len(job.description) >= 120:
        score += 1
        reasons.append("useful description (+1)")
    if job.link_status in {"200", "redirect", "protected"}:
        score += 1
        reasons.append("application page reachable (+1)")

    if re.search(r"\b(?:guaranteed income|instant earnings|no work required|get rich)\b", text):
        score = -100
        reasons = ["rejected: suspicious earnings claim"]

    job.quality_score = score
    job.quality_reasons = reasons
    return job


def accepted(job: Job, settings: Settings) -> bool:
    if settings.require_known_location and job.remote_scope == "unknown":
        return False
    if settings.link_check_enabled and job.link_status == "unchecked":
        return False
    return job.quality_score >= settings.min_quality_score

