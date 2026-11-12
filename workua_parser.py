"""Work.ua job search parser.

Design notes:
* Job links are recognised by URL pattern (/jobs/<numeric id>/), not by CSS
  classes, because class names change often and broke the old version.
* Real errors (blocked, network, bad status) raise WorkUaError so the bot can
  tell the user what actually happened instead of "no jobs found".
* Results are cached for a few minutes to keep the request volume low.
"""

import logging
import re
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.work.ua"
REQUEST_TIMEOUT = 15
CACHE_TTL_SECONDS = 600
CACHE_MAX_ITEMS = 200
MAX_QUERY_LENGTH = 100

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.8",
}

# Matches /jobs/4878388/, /en/jobs/4878388/, /ru/jobs/4878388/ and absolute forms
JOB_HREF_RE = re.compile(r"^(?:https?://(?:www\.)?work\.ua)?(?:/(?:en|ru))?/jobs/(\d+)/?")
SALARY_RE = re.compile(
    r"(\d[\d\s\u00a0\u202f]*(?:\s*[–-]\s*\d[\d\s\u00a0\u202f]*)?\s*(?:грн|UAH))"
)
BLOCK_MARKERS = ("captcha", "just a moment", "access denied", "cf-chl")


class WorkUaError(Exception):
    """Work.ua could not be queried (network problem, blocked, bad status)."""


@dataclass(frozen=True)
class Job:
    title: str
    url: str
    salary: Optional[str] = None


_session = requests.Session()
_session.headers.update(HEADERS)
_cache: dict = {}


def normalize_query(query: str) -> str:
    """Trim, collapse whitespace, lowercase, limit length."""
    return " ".join((query or "").split()).lower()[:MAX_QUERY_LENGTH]


def build_search_url(query: str) -> str:
    return f"{BASE_URL}/jobs-{quote_plus(query)}/"


def _clean_salary(raw: str) -> str:
    return " ".join(raw.replace("\u00a0", " ").replace("\u202f", " ").split())


def _find_salary(anchor) -> Optional[str]:
    """Look for a salary inside the job's card, only if the card holds one job."""
    card = anchor.find_parent(
        lambda tag: tag.name == "div" and "card" in (tag.get("class") or [])
    )
    if card is None:
        return None
    ids = {
        m.group(1)
        for a in card.find_all("a", href=True)
        if (m := JOB_HREF_RE.match(a["href"]))
    }
    if len(ids) != 1:
        return None
    match = SALARY_RE.search(card.get_text(" ", strip=True))
    return _clean_salary(match.group(1)) if match else None


def parse_jobs(html: str, limit: int = 10) -> list:
    """Extract jobs from a Work.ua search results page."""
    soup = BeautifulSoup(html, "html.parser")

    def collect(anchors) -> dict:
        found = {}
        for a in anchors:
            m = JOB_HREF_RE.match(a.get("href", ""))
            if not m:
                continue
            job_id = m.group(1)
            title = a.get_text(" ", strip=True)
            if not title or job_id in found:
                continue
            found[job_id] = (title, a)
        return found

    # Titles are links inside headings. Fall back to any matching link.
    found = collect(soup.select("h1 a[href], h2 a[href], h3 a[href]"))
    if not found:
        found = collect(soup.find_all("a", href=True))

    jobs = []
    for job_id, (title, anchor) in found.items():
        jobs.append(
            Job(
                title=title[:150],
                url=f"{BASE_URL}/jobs/{job_id}/",
                salary=_find_salary(anchor),
            )
        )
        if len(jobs) >= limit:
            break
    return jobs


def _looks_blocked(html: str) -> bool:
    head = html[:5000].lower()
    return any(marker in head for marker in BLOCK_MARKERS)


def _fetch(url: str) -> requests.Response:
    last_error = None
    for attempt in range(2):
        try:
            response = _session.get(url, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            last_error = e
            logger.warning("Request attempt %d failed: %s", attempt + 1, e)
            time.sleep(1)
            continue
        if response.status_code >= 500 and attempt == 0:
            logger.warning("Work.ua returned %s, retrying", response.status_code)
            time.sleep(1)
            continue
        return response
    raise WorkUaError(f"Network error: {last_error}")


def search_workua_jobs(query: str, max_results: int = 10) -> list:
    """Return up to max_results Job objects. Raises WorkUaError on failure."""
    query = normalize_query(query)
    if not query:
        return []

    key = f"{query}|{max_results}"
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    url = build_search_url(query)
    response = _fetch(url)
    status = response.status_code

    if status == 404:
        jobs = []
    elif status in (403, 429):
        raise WorkUaError(f"Work.ua blocked the request (HTTP {status}).")
    elif status != 200:
        raise WorkUaError(f"Work.ua returned HTTP {status}.")
    else:
        jobs = parse_jobs(response.text, max_results)
        if not jobs and _looks_blocked(response.text):
            raise WorkUaError("Work.ua returned a verification/captcha page.")
        if not jobs:
            logger.warning("0 jobs parsed for %r (page length %d)", query, len(response.text))

    if len(_cache) >= CACHE_MAX_ITEMS:
        _cache.pop(next(iter(_cache)))
    _cache[key] = (time.time(), jobs)
    return jobs
