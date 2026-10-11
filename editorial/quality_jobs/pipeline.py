from __future__ import annotations

import logging
import math
from collections import Counter
from itertools import zip_longest
from concurrent.futures import ThreadPoolExecutor, as_completed

from .classify import classify, is_automation
from .config import Settings
from .formatting import build_telegram_post
from .linkcheck import check_link
from .models import Job
from .scoring import accepted, score_job
from .sources import verify_candidate_details
from .text import canonicalize_url, fingerprint

LOGGER = logging.getLogger(__name__)


def _prepare(job: Job, settings: Settings) -> Job:
    job.canonical_url = canonicalize_url(job.direct_url)
    job.fingerprint = fingerprint(job.title, job.company)
    classify(job)
    score_job(job, settings)
    return job


def _worth_checking(job: Job, settings: Settings) -> bool:
    return (
        job.quality_score > -100
        and (not settings.require_known_location or job.remote_scope != "unknown")
        and job.quality_score >= settings.min_quality_score - 1
    )


def enrich(job: Job, settings: Settings) -> Job:
    _prepare(job, settings)
    worth_checking = (
        settings.link_check_enabled and _worth_checking(job, settings)
    )
    if worth_checking:
        job.link_status = check_link(
            job.direct_url,
            timeout=settings.request_timeout_seconds,
            user_agent=settings.user_agent,
        )
    score_job(job, settings)
    job.telegram_post = build_telegram_post(job)
    return job


def _verify_and_check(job: Job, settings: Settings) -> str:
    details_verified = verify_candidate_details(job, settings)
    _prepare(job, settings)
    if not details_verified:
        job.remote_scope = "unknown"
        job.africa_eligible = False
        score_job(job, settings)
    if not _worth_checking(job, settings):
        return "unchecked"
    return check_link(
        job.direct_url,
        timeout=settings.request_timeout_seconds,
        user_agent=settings.user_agent,
    )


def _balanced_limit(jobs: list[Job], settings: Settings) -> list[Job]:
    selected: list[Job] = []
    source_counts: Counter[str] = Counter()
    referral_limit = (
        max(1, math.floor(settings.max_per_run * settings.max_referral_share))
        if settings.max_referral_share > 0
        else 0
    )
    referral_count = 0
    ranked = sorted(jobs, key=lambda item: item.quality_score, reverse=True)

    def add_from(pool: list[Job], limit: int) -> None:
        nonlocal referral_count
        added = 0
        for job in pool:
            if len(selected) >= settings.max_per_run or added >= limit:
                break
            if job in selected or source_counts[job.source] >= settings.max_per_source:
                continue
            if job.is_referral and referral_count >= referral_limit:
                continue
            selected.append(job)
            source_counts[job.source] += 1
            referral_count += int(job.is_referral)
            added += 1

    entry_target = math.ceil(settings.max_per_run * settings.entry_priority_share)
    ai_target = math.ceil(settings.max_per_run * settings.ai_priority_share)
    add_from([job for job in ranked if job.experience_level == "entry"
              and (job.category == "ai" or is_automation(job))], entry_target)
    add_from([job for job in ranked if job.category == "ai"], ai_target)
    add_from([job for job in ranked if job.experience_level == "entry"], entry_target)
    add_from(ranked, settings.max_per_run)
    return sorted(selected, key=lambda item: item.quality_score, reverse=True)


def process(
    jobs: list[Job],
    settings: Settings,
    existing_urls: set[str] | None = None,
    existing_fingerprints: set[str] | None = None,
) -> tuple[list[Job], list[Job]]:
    seen_urls = set(existing_urls or set())
    seen_fingerprints = set(existing_fingerprints or set())
    prepared = [_prepare(job, settings) for job in jobs]
    if settings.link_check_enabled:
        candidate_pool = sorted(
            (job for job in prepared if _worth_checking(job, settings)),
            key=lambda item: item.quality_score,
            reverse=True,
        )
        # Alternate AI and entry candidates so neither fills the verification
        # budget before the other gets checked. Keep quality ordering in each.
        ai_pool = sorted([job for job in candidate_pool if job.category == "ai"],
                         key=lambda job: job.experience_level != "entry")
        entry_pool = sorted([job for job in candidate_pool if job.experience_level == "entry"],
                            key=lambda job: not (job.category == "ai" or is_automation(job)))
        priority_pool = [
            job for pair in zip_longest(ai_pool, entry_pool)
            for job in pair if job is not None
        ] + candidate_pool
        candidates: list[Job] = []
        candidate_source_counts: Counter[str] = Counter()
        candidate_urls: set[str] = set()
        candidate_fingerprints: set[str] = set()
        for job in priority_pool:
            if len(candidates) >= settings.max_per_run * 2:
                break
            if (job.canonical_url in seen_urls or job.fingerprint in seen_fingerprints
                    or job.canonical_url in candidate_urls
                    or job.fingerprint in candidate_fingerprints):
                continue
            if candidate_source_counts[job.source] >= settings.max_per_source * 2:
                continue
            candidates.append(job)
            candidate_urls.add(job.canonical_url)
            candidate_fingerprints.add(job.fingerprint)
            candidate_source_counts[job.source] += 1
        workers = min(12, len(candidates))
        if workers:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(_verify_and_check, job, settings): job
                    for job in candidates
                }
                for future in as_completed(futures):
                    futures[future].link_status = future.result()

    for job in prepared:
        score_job(job, settings)
        job.telegram_post = build_telegram_post(job)

    accepted_jobs: list[Job] = []
    rejected_jobs: list[Job] = []

    for job in prepared:
        if not job.canonical_url:
            job.quality_score = -100
            job.quality_reasons = ["rejected: missing URL"]
        if job.canonical_url in seen_urls or job.fingerprint in seen_fingerprints:
            job.quality_score = -100
            job.quality_reasons = ["rejected: duplicate"]
        if accepted(job, settings):
            accepted_jobs.append(job)
            seen_urls.add(job.canonical_url)
            seen_fingerprints.add(job.fingerprint)
        else:
            rejected_jobs.append(job)

    selected = _balanced_limit(accepted_jobs, settings)
    overflow = [job for job in accepted_jobs if job not in selected]
    for job in overflow:
        job.quality_reasons.append("held: per-run/source/referral balance limit")
    rejected_jobs.extend(overflow)
    LOGGER.info("accepted=%d rejected_or_held=%d", len(selected), len(rejected_jobs))
    return selected, rejected_jobs

