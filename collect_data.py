"""
collect_data.py
---------------
Fetches live AI job postings from two free public APIs:
  1. Adzuna API  — https://developer.adzuna.com
  2. USAJobs API — https://www.usajobs.gov/developer/

Both data sources are merged into a single raw CSV that is then
consumed by process_data.py for cleaning and enrichment.

Run:
    python collect_data.py

Prerequisites:
    Copy .env.example → .env and fill in your Adzuna credentials.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

import config

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retry decorator shared by all API calls
# ---------------------------------------------------------------------------
def _make_retry_decorator():
    """Return a tenacity retry decorator using settings from config."""
    return retry(
        reraise=True,
        stop=stop_after_attempt(config.RETRY_ATTEMPTS),
        wait=wait_fixed(config.RETRY_WAIT_SECONDS),
        retry=retry_if_exception_type(requests.RequestException),
    )

retry_on_request_error = _make_retry_decorator()


# ---------------------------------------------------------------------------
# Adzuna helpers
# ---------------------------------------------------------------------------

@retry_on_request_error
def _adzuna_fetch_page(
    country: str,
    search_term: str,
    page: int,
    session: requests.Session,
) -> dict[str, Any]:
    """
    Fetch a single page of Adzuna job results.

    Parameters
    ----------
    country : str
        Two-letter country code accepted by Adzuna (e.g. 'us', 'gb').
    search_term : str
        Job title / keyword to search for.
    page : int
        1-based page index.
    session : requests.Session
        Shared HTTP session with credentials pre-configured.

    Returns
    -------
    dict
        Raw JSON response from the Adzuna API.
    """
    url = f"{config.ADZUNA_BASE_URL}/{country}/search/{page}"
    params: dict[str, Any] = {
        "app_id": config.ADZUNA_APP_ID,
        "app_key": config.ADZUNA_APP_KEY,
        "what": search_term,
        "results_per_page": config.ADZUNA_RESULTS_PER_PAGE,
        "content-type": "application/json",
    }
    response = session.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def _parse_adzuna_jobs(
    raw: dict[str, Any],
    country: str,
    search_term: str,
) -> list[dict[str, Any]]:
    """
    Flatten Adzuna API results into a list of normalised job dicts.

    Parameters
    ----------
    raw : dict
        Raw JSON response body from the Adzuna API.
    country : str
        Country code used in the query (used to tag currency).
    search_term : str
        Original search term (kept for provenance).

    Returns
    -------
    list[dict]
        Each dict represents one job posting with a consistent schema.
    """
    jobs: list[dict[str, Any]] = []
    for item in raw.get("results", []):
        location_parts: list[str] = []
        loc = item.get("location", {})
        area = loc.get("area", [])
        if isinstance(area, list) and area:
            location_parts = area  # e.g. ["London", "Greater London"]
        location_display = ", ".join(location_parts) if location_parts else ""

        jobs.append(
            {
                "job_title": item.get("title", ""),
                "company": item.get("company", {}).get("display_name", ""),
                "country": config.COUNTRY_NAME_MAP.get(country, country.upper()),
                "city": location_parts[-1] if location_parts else "",
                "salary_min": item.get("salary_min"),
                "salary_max": item.get("salary_max"),
                "currency": config.COUNTRY_CURRENCY.get(country, "USD"),
                "posted_date": item.get("created", ""),
                "contract_type": item.get("contract_type", ""),
                "category": item.get("category", {}).get("label", ""),
                "job_description": item.get("description", ""),
                "source": "Adzuna",
                "search_term": search_term,
                "location_display": location_display,
            }
        )
    return jobs


def collect_adzuna(session: requests.Session) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Iterate over all configured countries and search terms to collect
    Adzuna job postings.

    Parameters
    ----------
    session : requests.Session
        Authenticated HTTP session.

    Returns
    -------
    tuple[list[dict], list[str]]
        (list of raw job dicts, list of error messages encountered)
    """
    all_jobs: list[dict[str, Any]] = []
    errors: list[str] = []

    for country in config.ADZUNA_COUNTRIES:
        for term in config.ADZUNA_SEARCH_TERMS:
            term_jobs: list[dict[str, Any]] = []
            for page in range(1, config.ADZUNA_MAX_PAGES + 1):
                try:
                    raw = _adzuna_fetch_page(country, term, page, session)
                    page_jobs = _parse_adzuna_jobs(raw, country, term)
                    if not page_jobs:
                        break  # No more results for this search
                    term_jobs.extend(page_jobs)
                    time.sleep(config.RATE_LIMIT_SLEEP)
                except Exception as exc:
                    msg = f"Adzuna error [{country} | {term} | page {page}]: {exc}"
                    log.warning(msg)
                    errors.append(msg)
                    break  # Skip remaining pages on error, continue next term

            print(
                f"Fetching '{term}' from {country.upper()}... "
                f"{len(term_jobs)} jobs found"
            )
            all_jobs.extend(term_jobs)

    return all_jobs, errors


# ---------------------------------------------------------------------------
# USAJobs helpers
# ---------------------------------------------------------------------------

@retry_on_request_error
def _usajobs_fetch_page(
    keyword: str,
    page: int,
    session: requests.Session,
) -> dict[str, Any]:
    """
    Fetch a single page of results from the USAJobs API.

    Parameters
    ----------
    keyword : str
        Position keywords to search for.
    page : int
        1-based page number.
    session : requests.Session
        HTTP session with required headers pre-set.

    Returns
    -------
    dict
        Raw JSON response from the USAJobs API.
    """
    params: dict[str, Any] = {
        "Keyword": keyword,
        "ResultsPerPage": 50,
        "Page": page,
    }
    response = session.get(config.USAJOBS_BASE_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def _parse_usajobs(
    raw: dict[str, Any],
    keyword: str,
) -> list[dict[str, Any]]:
    """
    Flatten USAJobs API results into normalised job dicts.

    Parameters
    ----------
    raw : dict
        Raw JSON response from USAJobs.
    keyword : str
        Original keyword used in the query.

    Returns
    -------
    list[dict]
        Normalised job posting records.
    """
    jobs: list[dict[str, Any]] = []
    search_result = raw.get("SearchResult", {})
    items = search_result.get("SearchResultItems", [])

    for item in items:
        matched = item.get("MatchedObjectDescriptor", {})
        remuneration = matched.get("PositionRemuneration", [{}])[0]
        schedule_list = matched.get("PositionSchedule", [{}])
        schedule = schedule_list[0].get("Name", "") if schedule_list else ""

        jobs.append(
            {
                "job_title": matched.get("PositionTitle", ""),
                "company": matched.get("OrganizationName", ""),
                "country": "United States",
                "city": matched.get("PositionLocationDisplay", ""),
                "salary_min": remuneration.get("MinimumRange"),
                "salary_max": remuneration.get("MaximumRange"),
                "currency": "USD",
                "posted_date": matched.get("PublicationStartDate", ""),
                "contract_type": schedule,
                "category": "Government",
                "job_description": matched.get("QualificationSummary", ""),
                "source": "USAJobs",
                "search_term": keyword,
                "location_display": matched.get("PositionLocationDisplay", ""),
            }
        )
    return jobs


def collect_usajobs(session: requests.Session) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Collect government AI job postings from USAJobs across all configured
    search terms.

    Parameters
    ----------
    session : requests.Session
        HTTP session with USAJobs headers already set.

    Returns
    -------
    tuple[list[dict], list[str]]
        (list of raw job dicts, list of error messages encountered)
    """
    all_jobs: list[dict[str, Any]] = []
    errors: list[str] = []

    for keyword in config.USAJOBS_SEARCH_TERMS:
        term_jobs: list[dict[str, Any]] = []
        for page in range(1, 5):  # max 4 pages = 200 results
            try:
                raw = _usajobs_fetch_page(keyword, page, session)
                page_jobs = _parse_usajobs(raw, keyword)
                if not page_jobs:
                    break
                term_jobs.extend(page_jobs)
                time.sleep(config.RATE_LIMIT_SLEEP)
            except Exception as exc:
                msg = f"USAJobs error [{keyword} | page {page}]: {exc}"
                log.warning(msg)
                errors.append(msg)
                break

        print(f"Fetching '{keyword}' from USAJobs... {len(term_jobs)} jobs found")
        all_jobs.extend(term_jobs)

    return all_jobs, errors


# ---------------------------------------------------------------------------
# Collection log
# ---------------------------------------------------------------------------

def save_collection_log(
    all_jobs: list[dict[str, Any]],
    errors: list[str],
    start_time: datetime,
) -> None:
    """
    Persist a JSON log summarising this collection run.

    Parameters
    ----------
    all_jobs : list[dict]
        Complete list of raw job records collected.
    errors : list[str]
        Any error messages encountered during collection.
    start_time : datetime
        UTC timestamp when collection started.
    """
    df = pd.DataFrame(all_jobs)

    jobs_per_source: dict[str, int] = {}
    jobs_per_country: dict[str, int] = {}

    if not df.empty:
        jobs_per_source = df["source"].value_counts().to_dict()
        jobs_per_country = df["country"].value_counts().to_dict()

    log_data: dict[str, Any] = {
        "timestamp": start_time.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "total_jobs_collected": len(all_jobs),
        "jobs_per_source": jobs_per_source,
        "jobs_per_country": jobs_per_country,
        "errors_count": len(errors),
        "errors": errors,
    }

    with open(config.COLLECTION_LOG, "w", encoding="utf-8") as fh:
        json.dump(log_data, fh, indent=2, ensure_ascii=False)

    log.info("Collection log saved → %s", config.COLLECTION_LOG)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Orchestrate the full data collection pipeline:
      1. Validate credentials.
      2. Collect from Adzuna.
      3. Collect from USAJobs.
      4. Merge and save raw CSV.
      5. Write collection log.
    """
    start_time = datetime.now(timezone.utc)
    log.info("=== AI Job Market Collection Started ===")

    # ------------------------------------------------------------------
    # Guard: ensure Adzuna credentials are present
    # ------------------------------------------------------------------
    if not config.ADZUNA_APP_ID or not config.ADZUNA_APP_KEY:
        log.error(
            "ADZUNA_APP_ID and ADZUNA_APP_KEY must be set in your .env file.\n"
            "Get free credentials at https://developer.adzuna.com"
        )
        raise SystemExit(1)

    all_jobs: list[dict[str, Any]] = []
    all_errors: list[str] = []

    # ------------------------------------------------------------------
    # Adzuna collection
    # ------------------------------------------------------------------
    log.info("--- Adzuna API ---")
    adzuna_session = requests.Session()
    adzuna_jobs, adzuna_errors = collect_adzuna(adzuna_session)
    all_jobs.extend(adzuna_jobs)
    all_errors.extend(adzuna_errors)
    log.info("Adzuna total: %d jobs collected", len(adzuna_jobs))

    # ------------------------------------------------------------------
    # USAJobs collection
    # ------------------------------------------------------------------
    log.info("--- USAJobs API ---")
    usajobs_session = requests.Session()
    usajobs_headers: dict[str, str] = {
        "Host": "data.usajobs.gov",
        "User-Agent": config.USAJOBS_USER_AGENT,
    }
    if config.USAJOBS_AUTH_KEY:
        usajobs_headers["Authorization-Key"] = config.USAJOBS_AUTH_KEY
    usajobs_session.headers.update(usajobs_headers)
    usajobs_jobs, usajobs_errors = collect_usajobs(usajobs_session)
    all_jobs.extend(usajobs_jobs)
    all_errors.extend(usajobs_errors)
    log.info("USAJobs total: %d jobs collected", len(usajobs_jobs))

    # ------------------------------------------------------------------
    # Persist raw data
    # ------------------------------------------------------------------
    if not all_jobs:
        log.warning("No jobs collected. Check your credentials and network.")
    else:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        raw_path = os.path.join(config.DATA_DIR, "raw_jobs.csv")
        df = pd.DataFrame(all_jobs)
        df.to_csv(raw_path, index=False, encoding="utf-8")
        log.info("Raw data saved → %s  (%d rows)", raw_path, len(df))

    # ------------------------------------------------------------------
    # Collection log
    # ------------------------------------------------------------------
    save_collection_log(all_jobs, all_errors, start_time)

    log.info(
        "=== Collection Complete: %d total jobs, %d errors ===",
        len(all_jobs),
        len(all_errors),
    )


if __name__ == "__main__":
    main()
