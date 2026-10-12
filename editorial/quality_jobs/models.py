from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(slots=True)
class Job:
    source: str
    title: str
    company: str
    location: str
    direct_url: str
    published_at: datetime | None = None
    description: str = ""
    salary: str = ""
    pay_currency: str = ""
    pay_period: str = ""
    pay_min: float | None = None
    pay_max: float | None = None
    location_reviewed: bool = False
    pay_reviewed: bool = False
    employment_type: str = ""
    source_job_id: str = ""
    category: str = "tech"
    opportunity_type: str = "job"
    experience_level: str = "not_specified"
    remote_scope: str = "unknown"
    africa_eligible: bool = False
    referral_url: str = ""
    referral_disclosure: str = ""
    canonical_url: str = ""
    fingerprint: str = ""
    search_keywords: str = ""
    quality_score: int = 0
    quality_reasons: list[str] = field(default_factory=list)
    link_status: str = "unchecked"
    telegram_post: str = ""
    evidence_lines: list[str] = field(default_factory=list)
    work_hours: str = ""
    telegram_featured: bool = False
    active_status: str = ""
    expires_at: datetime | None = None
    scraped_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def effective_url(self) -> str:
        return self.referral_url or self.direct_url

    @property
    def is_referral(self) -> bool:
        return bool(self.referral_url)

