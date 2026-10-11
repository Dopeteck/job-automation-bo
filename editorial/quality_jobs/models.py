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
    scraped_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def effective_url(self) -> str:
        return self.referral_url or self.direct_url

    @property
    def is_referral(self) -> bool:
        return bool(self.referral_url)

