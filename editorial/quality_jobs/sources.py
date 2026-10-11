from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from .config import Settings
from .models import Job
from .text import clean_text

LOGGER = logging.getLogger(__name__)


def _date(value: object) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)) or str(value).isdigit():
        try:
            numeric = float(value)
            # Accept both seconds and milliseconds since Unix epoch.
            if numeric > 10_000_000_000:
                numeric /= 1000
            return datetime.fromtimestamp(numeric, tz=timezone.utc)
        except (ValueError, TypeError, OverflowError, OSError):
            return None
    try:
        parsed = date_parser.parse(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        try:
            return parsedate_to_datetime(str(value)).astimezone(timezone.utc)
        except (ValueError, TypeError, OverflowError):
            return None


def fetch_remotive(settings: Settings) -> list[Job]:
    response = requests.get(
        "https://remotive.com/api/remote-jobs?limit=100",
        timeout=settings.request_timeout_seconds,
        headers={"User-Agent": settings.user_agent},
    )
    response.raise_for_status()
    jobs = []
    for item in response.json().get("jobs", []):
        jobs.append(
            Job(
                source="Remotive",
                source_job_id=str(item.get("id", "")),
                title=clean_text(item.get("title"), 160),
                company=clean_text(item.get("company_name"), 120),
                location=clean_text(item.get("candidate_required_location"), 160),
                direct_url=str(item.get("url", "")),
                published_at=_date(item.get("publication_date")),
                description=clean_text(item.get("description"), 8000),
                salary=clean_text(item.get("salary"), 100),
                employment_type=clean_text(item.get("job_type"), 80),
            )
        )
    return jobs


def fetch_remoteok(settings: Settings) -> list[Job]:
    response = requests.get(
        "https://remoteok.com/api",
        timeout=settings.request_timeout_seconds,
        headers={"User-Agent": settings.user_agent},
    )
    response.raise_for_status()
    payload = response.json()
    jobs = []
    for item in payload:
        if not isinstance(item, dict) or not item.get("position"):
            continue
        salary = ""
        if item.get("salary_min") or item.get("salary_max"):
            salary = f"${item.get('salary_min') or '?'}–${item.get('salary_max') or '?'}"
        jobs.append(
            Job(
                source="RemoteOK",
                source_job_id=str(item.get("id", "")),
                title=clean_text(item.get("position"), 160),
                company=clean_text(item.get("company"), 120),
                location=clean_text(item.get("location"), 160) or "Remote",
                direct_url=str(item.get("url", "")),
                published_at=_date(item.get("date") or item.get("epoch")),
                description=clean_text(item.get("description"), 8000),
                salary=salary,
                employment_type="Remote",
            )
        )
    return jobs


def _rss(settings: Settings, source: str, url: str) -> list[Job]:
    response = requests.get(
        url,
        timeout=settings.request_timeout_seconds,
        headers={"User-Agent": settings.user_agent},
    )
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    jobs = []
    for item in feed.entries[:80]:
        title = clean_text(item.get("title"), 180)
        company = clean_text(item.get("author"), 120)
        # Several job RSS feeds use "Role: Company" or "Company: Role".
        if not company and ":" in title:
            possible_company, possible_title = title.split(":", 1)
            if len(possible_company) < 80:
                company, title = possible_company.strip(), possible_title.strip()
        jobs.append(
            Job(
                source=source,
                source_job_id=str(item.get("id") or item.get("guid") or ""),
                title=title,
                company=company or source,
                location=clean_text(item.get("location"), 160) or "Remote",
                direct_url=str(item.get("link", "")),
                published_at=_date(item.get("published") or item.get("updated")),
                description=clean_text(
                    item.get("summary") or item.get("description") or item.get("content"),
                    8000,
                ),
            )
        )
    return jobs


def fetch_weworkremotely(settings: Settings) -> list[Job]:
    return _rss(
        settings,
        "WeWorkRemotely",
        "https://weworkremotely.com/remote-jobs.rss",
    )


def fetch_web3career(settings: Settings) -> list[Job]:
    """Compatibility alias retained for older CLI calls."""
    return fetch_cryptocurrencyjobs(settings)


def fetch_cryptocurrencyjobs(settings: Settings) -> list[Job]:
    jobs = _rss(
        settings,
        "CryptocurrencyJobs",
        "https://cryptocurrencyjobs.co/index.xml",
    )
    for job in jobs:
        if " at " in job.title:
            title, company = job.title.rsplit(" at ", 1)
            job.title = title.strip()
            job.company = company.strip()
    return jobs


def verify_candidate_details(job: Job, settings: Settings) -> bool:
    """Verify location claims that are missing from an RSS summary."""
    if job.source.lower() != "cryptocurrencyjobs":
        return True
    try:
        response = requests.get(
            job.direct_url,
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        LOGGER.warning("source_detail_failed source=%s url=%s error=%s", job.source, job.direct_url, exc)
        return False

    soup = BeautifulSoup(response.text, "html.parser")
    main = soup.select_one("main")
    description = clean_text(str(main or soup), 8000)
    location_match = re.search(
        r"\bLocation\s*:\s*(.{1,160}?)(?=\s+(?:To be considered|Work Timezone|About the role)\b)",
        description,
        flags=re.IGNORECASE,
    )
    if not location_match:
        return False
    job.description = description
    job.location = clean_text(location_match.group(1), 160)
    return True


def fetch_arbeitnow(settings: Settings) -> list[Job]:
    response = requests.get(
        "https://www.arbeitnow.com/api/job-board-api",
        timeout=settings.request_timeout_seconds,
        headers={"User-Agent": settings.user_agent},
    )
    response.raise_for_status()
    jobs = []
    for item in response.json().get("data", []):
        if not item.get("remote"):
            continue
        tags = ", ".join(str(tag) for tag in item.get("tags", []))
        jobs.append(
            Job(
                source="Arbeitnow",
                source_job_id=str(item.get("slug", "")),
                title=clean_text(item.get("title"), 160),
                company=clean_text(item.get("company_name"), 120),
                location=clean_text(item.get("location"), 160) or tags or "Remote",
                direct_url=str(item.get("url", "")),
                published_at=_date(item.get("created_at")),
                description=clean_text(item.get("description"), 8000),
                employment_type=", ".join(
                    str(kind) for kind in item.get("job_types", [])
                ),
            )
        )
    return jobs


def fetch_crowdgen(settings: Settings) -> list[Job]:
    """Read current project pages from CrowdGen's public WordPress API."""
    response = requests.get(
        "https://crowdgen.com/wp-json/wp/v2/pages",
        params={
            "per_page": 30,
            "orderby": "date",
            "order": "desc",
            "_fields": "id,date_gmt,date,slug,link,title,content",
        },
        timeout=max(25, settings.request_timeout_seconds),
        headers={"User-Agent": settings.user_agent},
    )
    response.raise_for_status()
    jobs = []
    for item in response.json():
        title = clean_text(item.get("title", {}).get("rendered"), 180)
        slug = str(item.get("slug", ""))
        lowered = f"{title} {slug}".lower()
        looks_like_project = (
            title.lower().startswith("project ")
            or "speakers wanted" in lowered
            or any(
                term in lowered
                for term in ("evaluator", "data label", "annotator", "voice recording")
            )
        )
        if not looks_like_project or any(
            term in lowered for term in ("referral", "popup", "template")
        ):
            continue
        description = clean_text(item.get("content", {}).get("rendered"), 8000)
        salary_match = re.search(
            r"\$\s?\d+(?:\.\d+)?(?:\s?[-–]\s?\$?\d+(?:\.\d+)?)?"
            r"\s*(?:per|/)\s*(?:hour|task|project)",
            description,
            flags=re.IGNORECASE,
        )
        location_match = re.search(
            r"(?:must reside in|based in|within)\s+([A-Za-z .,&-]{2,60})",
            description,
            flags=re.IGNORECASE,
        )
        jobs.append(
            Job(
                source="CrowdGen",
                source_job_id=str(item.get("id", slug)),
                title=title,
                company="CrowdGen by Appen",
                location=(
                    clean_text(location_match.group(1), 100) if location_match else title
                ),
                direct_url=str(item.get("link", "")),
                published_at=_date(item.get("date_gmt") or item.get("date")),
                description=description,
                salary=salary_match.group(0) if salary_match else "",
                employment_type="Remote project",
                opportunity_type="ai_gig",
            )
        )
    return jobs


def fetch_mercor(settings: Settings) -> list[Job]:
    response = requests.get(
        "https://work.mercor.com/explore",
        timeout=settings.request_timeout_seconds,
        headers={"User-Agent": settings.user_agent},
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    state_script = soup.find("script", id="__NEXT_DATA__")
    if not state_script or not state_script.string:
        raise ValueError("Mercor public listings data was not found")

    import json

    state = json.loads(state_script.string)
    # Mercor can return a null dehydratedState instead of listing data.
    # Treat this as an unavailable source, not a fatal collection error.
    def as_dict(value):
        return value if isinstance(value, dict) else {}

    page_props = as_dict(as_dict(as_dict(state).get("props")).get("pageProps"))
    queries = as_dict(page_props.get("dehydratedState")).get("queries")
    if not isinstance(queries, list):
        raise ValueError("Mercor public listings data is temporarily unavailable")
    listings = None
    for query in queries:
        data = as_dict(as_dict(as_dict(query).get("state")).get("data"))
        if isinstance(data.get("listings"), list):
            listings = data["listings"]
            break
    if listings is None:
        raise ValueError("Mercor public listings format was not recognized")
    country_names = {
        "NGA": "Nigeria",
        "GHA": "Ghana",
        "KEN": "Kenya",
        "ZAF": "South Africa",
        "EGY": "Egypt",
        "USA": "United States",
        "CAN": "Canada",
        "GBR": "United Kingdom",
        "MEX": "Mexico",
        "BRA": "Brazil",
        "IND": "India",
        "IDN": "Indonesia",
        "JPN": "Japan",
        "KOR": "South Korea",
    }
    jobs = []
    for item in listings:
        if not isinstance(item, dict):
            continue
        listing_id = item.get("listingId")
        if (
            not listing_id
            or item.get("status") != "active"
            or item.get("deletedAt")
            or item.get("disableApplications")
        ):
            continue
        codes = list(
            dict.fromkeys(
                (item.get("eligibleResidenceLocation") or [])
                + (item.get("eligibleLocation") or [])
            )
        )
        locations = [country_names.get(code, code) for code in codes]
        location = ", ".join(locations) or clean_text(item.get("location"), 160)
        rate_min, rate_max = item.get("rateMin"), item.get("rateMax")
        frequency = item.get("payRateFrequency") or item.get("commitment") or ""
        salary = (
            f"${rate_min:g}–${rate_max:g}/{frequency}"
            if rate_min is not None and rate_max is not None
            else ""
        )
        jobs.append(
            Job(
                source="Mercor",
                source_job_id=str(listing_id),
                title=clean_text(item.get("title"), 160),
                company=clean_text(item.get("companyName") or "Mercor", 120),
                location=location,
                direct_url=f"https://work.mercor.com/jobs/{listing_id}",
                published_at=_date(item.get("postedAt") or item.get("createdAt")),
                description=clean_text(item.get("description"), 8000),
                salary=salary,
                employment_type=clean_text(item.get("commitment"), 80),
                referral_url=settings.mercor_referral_url,
                referral_disclosure=(
                    "We may earn if you are accepted and begin paid work."
                    if settings.mercor_referral_url
                    else ""
                ),
            )
        )
    return jobs


def _lever(settings: Settings, board: str, company: str) -> list[Job]:
    """Read direct remote vacancies, preserving dates and eligibility."""
    from .classify import AI_TERMS, AUTOMATION_TERMS
    response = requests.get(
        f"https://api.lever.co/v0/postings/{board}", params={"mode": "json"},
        timeout=max(25, settings.request_timeout_seconds),
        headers={"User-Agent": settings.user_agent},
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise ValueError(f"{company} public listings format was not recognized")
    jobs = []
    for item in data:
        if not isinstance(item, dict) or item.get("workplaceType") != "remote":
            continue
        categories = item.get("categories") or {}
        if not isinstance(categories, dict):
            continue
        parts = [item.get("descriptionPlain") or item.get("description"),
                 item.get("openingPlain"), item.get("additionalPlain")]
        parts.extend(f"{section.get('text', '')} {section.get('content', '')}"
                     for section in item.get("lists") or [] if isinstance(section, dict))
        description = clean_text(" ".join(str(part or "") for part in parts), 8000)
        title = clean_text(item.get("text"), 160)
        if not any(term in f"{title} {description}".lower()
                   for term in AI_TERMS | AUTOMATION_TERMS):
            continue
        locations = categories.get("allLocations") or [categories.get("location", "")]
        location = clean_text(", ".join(str(value) for value in locations if value), 300)
        country = {"US": "United States", "CA": "Canada", "GB": "United Kingdom",
                   "NG": "Nigeria", "IN": "India", "DE": "Germany",
                   "FR": "France", "AU": "Australia"}.get(item.get("country"))
        if country and country.lower() not in location.lower():
            location = f"{location}, {country}".strip(", ")
        salary_range = item.get("salaryRange") or {}
        salary = clean_text(item.get("salaryDescription"), 100)
        if isinstance(salary_range, dict) and salary_range.get("min") is not None:
            salary = (f"{salary_range.get('currency', '')} {salary_range['min']}"
                      f"–{salary_range.get('max', salary_range['min'])}"
                      f"/{salary_range.get('interval', '')}")
        jobs.append(Job(
            source=company, source_job_id=str(item.get("id", "")),
            title=title, company=company, location=location,
            direct_url=str(item.get("hostedUrl") or item.get("applyUrl") or ""),
            published_at=_date(item.get("createdAt")), description=description,
            salary=salary, employment_type=clean_text(categories.get("commitment"), 80),
        ))
    return jobs


def fetch_welo(settings: Settings) -> list[Job]:
    return _lever(settings, "weloglobal", "Welo Data / Welo Global")


def fetch_rws(settings: Settings) -> list[Job]:
    return _lever(settings, "rws", "RWS TrainAI")


def fetch_skyward(settings: Settings) -> list[Job]:
    return _lever(settings, "skywarditsolutions", "Skyward IT Solutions")


def fetch_minted(settings: Settings) -> list[Job]:
    return _lever(settings, "minted", "Minted")


SOURCE_FETCHERS: dict[str, Callable[[Settings], list[Job]]] = {
    "welo": fetch_welo,
    "rws": fetch_rws,
    "skyward": fetch_skyward,
    "minted": fetch_minted,
    "arbeitnow": fetch_arbeitnow,
    "cryptocurrencyjobs": fetch_cryptocurrencyjobs,
    "crowdgen": fetch_crowdgen,
    "remotive": fetch_remotive,
    "remoteok": fetch_remoteok,
    "weworkremotely": fetch_weworkremotely,
    "mercor": fetch_mercor,
}


def collect(settings: Settings, selected: set[str] | None = None) -> list[Job]:
    jobs: list[Job] = []
    for name, fetcher in SOURCE_FETCHERS.items():
        if selected and name not in selected:
            continue
        try:
            fetched = fetcher(settings)
            LOGGER.info("source=%s fetched=%d", name, len(fetched))
            jobs.extend(fetched)
        except (requests.RequestException, ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
            LOGGER.warning("source=%s failed=%s", name, exc)
    return jobs

