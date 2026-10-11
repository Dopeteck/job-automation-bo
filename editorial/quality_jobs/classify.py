from __future__ import annotations

import re

from .models import Job


AI_TERMS = {
    "ai data specialist",
    "ai data trainer",
    "ai evaluation",
    "ai linguistic evaluator",
    "speech ai",
    "ai engineer",
    "ai researcher",
    "ai safety",
    "model evaluation",
    "multimodal",
    "llm",
    "ai trainer",
    "ai training",
    "ai evaluator",
    "model evaluator",
    "llm evaluator",
    "prompt evaluator",
    "response evaluator",
    "data annotation",
    "data annotator",
    "data labeling",
    "rlhf",
    "machine learning",
    "artificial intelligence",
    "search quality rater",
    "ads quality rater",
    "speech collection",
    "voice recording",
    "media quality evaluator",
    "speakers wanted",
}

EASY_ENTRY_TERMS = {
    "entry level",
    "entry-level",
    "no experience required",
    "no prior experience",
    "junior",
    "intern",
    "internship",
    "apprentice",
    "trainee",
    "graduate",
    "technical support",
    "customer support",
    "help desk",
    "helpdesk",
    "manual qa",
    "qa tester",
    "software tester",
    "data annotator",
    "data annotation",
    "ai trainer",
    "ai evaluator",
    "model evaluator",
    "llm evaluator",
    "response evaluator",
    "search quality rater",
    "ads quality rater",
    "speech collection",
    "voice recording",
    "media quality evaluator",
    "speakers wanted",
    "transcription",
    "content moderator",
    "community moderator",
    "no-code",
    "nocode",
}

SENIOR_TERMS = {"senior", "staff", "principal", "lead", "manager", "director", "head of"}

AUTOMATION_TERMS = {
    "automation", "make.com", "zapier", "n8n", "no-code", "nocode",
    "workflow integration", "workflow builder",
}


def is_automation(job: Job) -> bool:
    if _contains(job.title.lower(), AUTOMATION_TERMS):
        return True
    description = job.description.lower()
    # General company copy about automation is not a workflow-building role.
    return bool(re.search(
        r"\b(?:build|develop|create|maintain|design|implement|automate|integrat)\w*"
        r"[^.;\n]{0,160}(?:make\.com|zapier|n8n|workflow automation|automated workflows|no-code)",
        description,
    ))


def experience_level(job: Job) -> str:
    title = job.title.lower()
    description = job.description.lower()
    if any(re.search(r"\b" + re.escape(term) + r"\b", title) for term in SENIOR_TERMS):
        return "senior"
    # Requirements outrank a junior title. Tool names or mentions of junior
    # colleagues do not by themselves demonstrate low experience requirements.
    years = [int(value) for value in re.findall(
        r"\b(\d{1,2})(?:\s*[-–]\s*\d{1,2})?\s*\+?\s*years?\b", description
    )]
    if years and max(years) > 2:
        return "mid"
    entry_title = any(re.search(r"\b" + re.escape(term) + r"\b", title)
                      for term in EASY_ENTRY_TERMS - {"no-code", "nocode"})
    explicit_entry = _contains(description, {
        "no experience required", "no prior experience", "entry-level role",
        "entry level role", "no professional experience", "no specialized technical experience",
    })
    specialist_requirements = bool(re.search(
        r"\b(ph\.?d|doctorate|doctoral|master['’]?s degree|board.certified)\b", description
    ))
    if (entry_title or explicit_entry) and not specialist_requirements:
        return "entry"
    return "not_specified"

WORLDWIDE_TERMS = {
    "worldwide",
    "world wide",
    "anywhere",
    "global remote",
    "remote globally",
    "any country",
}
AFRICA_TERMS = {
    "africa",
    "nigeria",
    "emea",
    "ghana",
    "kenya",
    "south africa",
    "egypt",
    "morocco",
}
LATAM_TERMS = {
    "latam", "latin america", "south america", "central america", "costa rica",
    "chile", "peru", "mexico", "brazil", "argentina", "colombia",
}
EUROPE_TERMS = {
    "europe", "european union", "emea", "uk/eu", "eu only", "denmark",
    "croatia", "czech", "georgia", "germany", "france", "italy", "spain",
    "portugal", "united kingdom",
}
US_TERMS = {
    "united states", "us only", "usa only", "u.s. only", "north america", "en-us",
    "vi-us",
}
ASIA_TERMS = {"asia", "apac", "india", "indonesia", "japan", "south korea", "philippines"}
MIDDLE_EAST_TERMS = {
    "middle east", "mena", "uae", "united arab emirates", "saudi arabia", "dubai",
    "ar-ae", "ar-sa", "ar-qa", "qatar",
}


def _contains(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def _region_scope(text: str) -> str | None:
    # Geography comes from the location field / explicit eligibility sentences,
    # not mentions of customers or offices elsewhere in the company description.
    def has(pattern: str) -> bool:
        return bool(re.search(pattern, text, re.I))

    us = has(r"\b(united states|usa|u\.s\.|us)\b|en-us|vi-us")
    canada = has(r"\bcanada\b")
    uk = has(r"\b(uk|united kingdom)\b")
    eu = has(r"\b(eu|european union)\b")
    if us and canada and uk and eu:
        return "us_ca_uk_eu"
    if us and canada and not uk and not eu:
        return "us_canada"
    if (us or canada) and has(r"\b(europe|africa|asia|apac|latam|brazil|india|australia|emea|mena)\b"):
        return None  # Mixed regions need clearer eligibility; never label US-only.
    if sum([us, canada, uk, eu]) == 1:
        return "us" if us else "canada" if canada else "uk" if uk else "eu"
    if uk and eu and not us and not canada:
        return "europe"
    if has(r"\bemea\b"):
        return "emea"
    groups = [
        ("africa", AFRICA_TERMS - {"emea"}),
        ("latam", LATAM_TERMS), ("europe", EUROPE_TERMS - {"emea"}),
        ("asia", ASIA_TERMS), ("middle_east", MIDDLE_EAST_TERMS),
        ("oceania", {"australia", "new zealand", "oceania"}),
    ]
    matches = [scope for scope, terms in groups if any(
        re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.I)
        for term in terms
    )]
    if len(matches) == 1 and not (us or canada or uk or eu):
        return matches[0]
    if has(r"\bnorth america\b") and not matches:
        return "us_canada"
    return None


def _explicitly_restricted_scope(text: str) -> str | None:
    snippets = re.findall(
        r"(?:location\s*:|must\s+reside|must\s+be\s+based|"
        r"must\s+be\s+(?:a\s+)?(?:u\.s\.|us|united states)\s+citizen|"
        r"(?:authorized|eligible)\s+to\s+work\s+in|"
        r"candidates?\s+(?:must\s+be|based|located)|"
        r"open\s+(?:only\s+)?to|remote\s+from)[^.;\n]{0,180}", text,
    )
    for snippet in snippets:
        scope = _region_scope(snippet)
        if scope:
            return scope
    return None


def classify(job: Job) -> Job:
    text = " ".join(
        [job.title, job.description, job.location, job.employment_type]
    ).lower()

    if _contains(text, AI_TERMS):
        job.category = "ai"
        if _contains(text, {"annotation", "labeling", "evaluator", "rater", "transcription"}):
            job.opportunity_type = "ai_gig"
    elif _contains(text, {"web3", "blockchain", "crypto", "solidity", "defi"}):
        job.category = "web3"
    else:
        job.category = "tech"

    job.experience_level = experience_level(job)

    location = job.location.lower().strip()
    restricted_scope = _explicitly_restricted_scope(text)
    location_scope = _region_scope(location)
    title_scope = _region_scope(job.title.lower()) if re.search(
        r"\([^)]*\)|\b(?:based|only)\b", job.title.lower()
    ) else None
    if restricted_scope:
        job.remote_scope = restricted_scope
    elif location_scope:
        job.remote_scope = location_scope
    elif title_scope:
        job.remote_scope = title_scope
    elif _contains(location, WORLDWIDE_TERMS):
        job.remote_scope = "worldwide"
    elif location in {"", "remote"} and _contains(job.description.lower(), WORLDWIDE_TERMS):
        job.remote_scope = "worldwide"
    else:
        job.remote_scope = "unknown"
    job.africa_eligible = job.remote_scope in {"worldwide", "africa", "emea"}

    # Mercor's published policy says unspecified listings default to US/CA/UK/EU.
    if job.source.lower() == "mercor" and job.remote_scope == "unknown":
        job.remote_scope = "us_ca_uk_eu"
        job.africa_eligible = False

    keywords = [job.title, job.category, job.experience_level, "remote job"]
    if job.remote_scope == "worldwide":
        keywords.append("worldwide")
    if job.africa_eligible:
        keywords.append("Africa friendly")
    job.search_keywords = ", ".join(dict.fromkeys(x for x in keywords if x))
    return job
