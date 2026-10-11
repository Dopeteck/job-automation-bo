from __future__ import annotations

import re

from .models import Job
from .classify import is_automation
from .text import safe_html, shorten


ROLE_PATTERNS = [
    ("#Design", r"\b(design(er)?|ux|ui)\b"),
    ("#Marketing", r"\b(marketing|growth|seo|content|social media)\b"),
    ("#Support", r"\b(support|customer success|help ?desk|moderator)\b"),
    ("#Developer", r"\b(developer|engineer|programmer|devops|solidity|architect)\b"),
    ("#Sales", r"\b(sales|account executive|business development)\b"),
    ("#Data", r"\b(data|analyst|analytics|scientist)\b"),
    ("#Operations", r"\b(operations|assistant|recruiter|finance|accountant)\b"),
]
REGION_TAGS = {
    "worldwide": "#Worldwide", "africa": "#Africa", "emea": "#EMEA",
    "europe": "#Europe", "eu": "#EUOnly", "uk": "#UKOnly",
    "us": "#USOnly", "canada": "#CanadaOnly", "us_canada": "#USCanada",
    "us_ca_uk_eu": "#USCanadaUKEU", "latam": "#LATAM",
    "asia": "#APAC", "middle_east": "#MENA", "oceania": "#Oceania",
    "unknown": "#CheckEligibility",
}


def role_tag(job: Job) -> str:
    title = job.title.lower()
    if is_automation(job):
        return "#Automation"
    for tag, pattern in ROLE_PATTERNS:
        if re.search(pattern, title):
            return tag
    return "#AITraining" if job.category == "ai" else "#OtherRoles"


def build_telegram_post(job: Job) -> str:
    # Keep the original location visible: a regional tag is only a filter,
    # not a promise that every country in that region can apply.
    scope_labels = {
        "worldwide": "Worldwide remote", "africa": "Africa remote",
        "emea": "EMEA remote", "europe": "Europe remote", "eu": "EU only",
        "us": "US only", "canada": "Canada only", "uk": "UK only",
        "us_canada": "US/Canada remote", "us_ca_uk_eu": "US/Canada/UK/EU",
        "latam": "LATAM remote", "asia": "Asia/APAC remote",
        "middle_east": "Middle East/MENA remote", "oceania": "Oceania remote",
    }
    scope = scope_labels.get(job.remote_scope, "Check location eligibility")
    location = shorten(job.location, 160)
    if location and location.lower() not in {"remote", "worldwide", "anywhere"}:
        scope += " — " + location
    strengths = []
    if job.salary:
        strengths.append("pay disclosed")
    if job.experience_level == "entry":
        strengths.append("lower stated experience requirements")
    if job.remote_scope == "worldwide":
        strengths.append("worldwide eligibility listed")
    if job.category == "ai":
        strengths.append("AI work")
    if not strengths:
        strengths.append("named employer; location eligibility listed")
    tags = [role_tag(job), REGION_TAGS.get(job.remote_scope, "#CheckEligibility")]
    if is_automation(job):
        tags.append("#AutomationJobs")
    if job.africa_eligible:
        tags.append("#AfricaEligible")
    if job.category == "ai":
        tags.append("#AIJobs")
    elif job.category == "web3":
        tags.append("#Web3Jobs")
    if job.experience_level == "entry":
        tags.append("#EntryLevel")
    lines = [
        f"<b>{safe_html(shorten(job.title, 110))}</b>",
        safe_html(shorten(job.company, 80)),
        f"💵 {safe_html(shorten(job.salary, 100)) if job.salary else 'Pay not disclosed'}",
        f"📍 {safe_html(scope)}",
        "",
        f"✅ Why it stands out: {safe_html('; '.join(strengths[:2]))}.",
        "",
        f'<a href="{safe_html(job.effective_url)}"><b>Apply here</b></a>',
    ]
    if job.is_referral:
        lines.append("<i>Referral: we may earn if you are accepted and begin paid work.</i>")
        if job.direct_url != job.referral_url:
            lines.append(f'<a href="{safe_html(job.direct_url)}">Original listing</a>')
    lines.extend(["", "🔖 Save this to Saved Messages to apply later.", " ".join(tags)])
    return "\n".join(lines)
