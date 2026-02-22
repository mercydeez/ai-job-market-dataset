"""
process_data.py
---------------
Cleans, enriches, and deduplicates raw job data collected by collect_data.py.

Transformations applied:
  - Skill extraction from job description
  - Experience level inference from title / description
  - Remote type inference from description / title
  - Salary normalisation → annual USD
  - Deduplication on (job_title, company, city)
  - Final column selection and CSV export

Run:
    python process_data.py

Input:
    data/raw_jobs.csv   (produced by collect_data.py)

Output:
    data/ai_jobs_global.csv
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

import pandas as pd

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
# Skill extraction
# ---------------------------------------------------------------------------

# Build a single compiled regex per keyword for fast, case-insensitive matching.
# Word boundaries prevent "R" from matching inside "Transformer" etc.
_SKILL_PATTERNS: dict[str, re.Pattern[str]] = {
    skill: re.compile(rf"\b{re.escape(skill)}\b", re.IGNORECASE)
    for skill in config.SKILL_KEYWORDS
}


def extract_skills(text: str) -> str:
    """
    Scan *text* for known AI/ML skill keywords and return them as a
    comma-separated string preserving the original keyword casing.

    Parameters
    ----------
    text : str
        Raw job description or combined title + description.

    Returns
    -------
    str
        Comma-separated skills found, e.g. ``"Python, SQL, PyTorch"``.
        Returns an empty string when no skills are matched.
    """
    if not isinstance(text, str):
        return ""
    found = [skill for skill, pat in _SKILL_PATTERNS.items() if pat.search(text)]
    return ", ".join(found)


# ---------------------------------------------------------------------------
# Experience level detection
# ---------------------------------------------------------------------------

_EXPERIENCE_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "Junior",
        re.compile(r"\b(junior|entry[- ]level?|entry|associate)\b", re.IGNORECASE),
    ),
    (
        "Senior",
        re.compile(r"\b(senior|sr\.?)\b", re.IGNORECASE),
    ),
    (
        "Lead",
        re.compile(r"\b(lead|principal|staff)\b", re.IGNORECASE),
    ),
    (
        "Management",
        re.compile(r"\b(manager|director|head|vp|vice president)\b", re.IGNORECASE),
    ),
]


def detect_experience_level(text: str) -> str:
    """
    Infer seniority from job title / description text.

    Rules are evaluated in order; the first match wins.  Falls back to
    ``"Mid-level"`` when no keywords are found.

    Parameters
    ----------
    text : str
        Concatenated job title and (optionally) description.

    Returns
    -------
    str
        One of: ``"Junior"``, ``"Senior"``, ``"Lead"``,
        ``"Management"``, ``"Mid-level"``.
    """
    if not isinstance(text, str):
        return "Mid-level"
    for level, pattern in _EXPERIENCE_RULES:
        if pattern.search(text):
            return level
    return "Mid-level"


# ---------------------------------------------------------------------------
# Remote type detection
# ---------------------------------------------------------------------------

_REMOTE_PATTERN = re.compile(r"\bremote\b", re.IGNORECASE)
_HYBRID_PATTERN = re.compile(r"\bhybrid\b", re.IGNORECASE)
_ONSITE_PATTERN = re.compile(r"\b(onsite|on-site|in-office)\b", re.IGNORECASE)


def detect_remote_type(text: str) -> str:
    """
    Classify the work arrangement from free-text.

    Parameters
    ----------
    text : str
        Job description and/or title.

    Returns
    -------
    str
        One of: ``"Remote"``, ``"Hybrid"``, ``"Onsite"``, ``"Unspecified"``.
    """
    if not isinstance(text, str):
        return "Unspecified"
    if _REMOTE_PATTERN.search(text):
        return "Remote"
    if _HYBRID_PATTERN.search(text):
        return "Hybrid"
    if _ONSITE_PATTERN.search(text):
        return "Onsite"
    return "Unspecified"


# ---------------------------------------------------------------------------
# Salary normalisation
# ---------------------------------------------------------------------------

def _to_float(value: object) -> Optional[float]:
    """
    Safely coerce a value to float, returning ``None`` on failure or when
    the value is zero (salary of 0 is treated as missing).

    Parameters
    ----------
    value : object
        Raw salary value (string, int, float, or None).

    Returns
    -------
    float or None
    """
    try:
        f = float(value)  # type: ignore[arg-type]
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def normalise_salary(
    salary: Optional[float],
    currency: str,
) -> Optional[float]:
    """
    Convert a salary figure to annual USD and round to the nearest 1 000.

    Monthly / weekly detection is heuristic:
      - If the value looks like a monthly figure (< 20 000 for non-USD,
        or < 15 000 for USD), multiply by 12.
    No estimation is performed for missing/zero values — they are left as
    ``NaN`` in the final DataFrame.

    Parameters
    ----------
    salary : float or None
        Salary amount in the original currency.
    currency : str
        ISO 4217 currency code, e.g. ``"GBP"``.

    Returns
    -------
    float or None
        Annual salary in USD, rounded to the nearest 1 000, or ``None``.
    """
    val = _to_float(salary)
    if val is None:
        return None

    rate = config.CURRENCY_TO_USD.get(currency.upper(), 1.0)
    usd = val * rate

    # Heuristic: if the converted value is suspiciously small treat as monthly
    if usd < 15_000:
        usd *= 12

    return round(usd / 1_000) * 1_000


# ---------------------------------------------------------------------------
# Core processing pipeline
# ---------------------------------------------------------------------------

def load_raw(path: str) -> pd.DataFrame:
    """
    Load the raw CSV produced by collect_data.py.

    Parameters
    ----------
    path : str
        File path to the raw CSV.

    Returns
    -------
    pd.DataFrame
        Loaded DataFrame.

    Raises
    ------
    FileNotFoundError
        If the raw CSV does not exist.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Raw data not found at '{path}'. "
            "Run collect_data.py first."
        )
    df = pd.read_csv(path, low_memory=False)
    log.info("Loaded %d raw rows from %s", len(df), path)
    return df


def process(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply the full cleaning and enrichment pipeline.

    Steps
    -----
    1. Drop rows with missing or empty job_title.
    2. Normalise posted_date to ISO date strings.
    3. Extract skills from job_description.
    4. Detect experience_level from title + description.
    5. Detect remote_type from description + title.
    6. Normalise salary columns to annual USD.
    7. Select and rename to the canonical output schema.
    8. Deduplicate on (job_title, company, city).

    Parameters
    ----------
    df : pd.DataFrame
        Raw job data with the schema produced by collect_data.py.

    Returns
    -------
    pd.DataFrame
        Cleaned, enriched DataFrame ready for CSV export.
    """
    # 1. Drop rows with null / empty job title ---------------------------------
    df = df.copy()
    df["job_title"] = df["job_title"].astype(str).str.strip()
    df = df[df["job_title"].notna() & (df["job_title"] != "") & (df["job_title"] != "nan")]
    log.info("After title filter: %d rows", len(df))

    # 2. Parse posted_date -----------------------------------------------------
    df["posted_date"] = pd.to_datetime(
        df["posted_date"], errors="coerce", utc=True
    ).dt.date.astype(str)
    df["posted_date"] = df["posted_date"].replace("NaT", "")

    # 3. Skill extraction ------------------------------------------------------
    # Combine title and description for richer matching
    combined_text = (
        df["job_title"].fillna("") + " " + df["job_description"].fillna("")
    )
    log.info("Extracting skills …")
    df["required_skills"] = combined_text.apply(extract_skills)

    # 4. Experience level ------------------------------------------------------
    log.info("Detecting experience levels …")
    df["experience_level"] = combined_text.apply(detect_experience_level)

    # 5. Remote type -----------------------------------------------------------
    log.info("Detecting remote type …")
    df["remote_type"] = combined_text.apply(detect_remote_type)

    # 6. Salary normalisation --------------------------------------------------
    log.info("Normalising salaries …")
    currency_col = df["currency"].fillna("USD")

    df["salary_min"] = [
        normalise_salary(s, c)
        for s, c in zip(df["salary_min"], currency_col)
    ]
    df["salary_max"] = [
        normalise_salary(s, c)
        for s, c in zip(df["salary_max"], currency_col)
    ]

    # 7. Select canonical columns ----------------------------------------------
    output_columns = [
        "job_title",
        "company",
        "country",
        "city",
        "salary_min",
        "salary_max",
        "currency",
        "remote_type",
        "experience_level",
        "required_skills",
        "posted_date",
        "source",
        "job_description",
    ]

    # Keep only columns that exist in this DataFrame
    available = [c for c in output_columns if c in df.columns]
    df = df[available]

    # Standardise currency to USD after conversion
    df["currency"] = "USD"

    # 8. Deduplication ---------------------------------------------------------
    before_dedup = len(df)
    df = df.drop_duplicates(subset=["job_title", "company", "city"], keep="first")
    log.info(
        "Deduplication: %d → %d rows (removed %d duplicates)",
        before_dedup,
        len(df),
        before_dedup - len(df),
    )

    # Reset index for clean CSV output
    df = df.reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Load raw data, run the processing pipeline, and save the final CSV.
    """
    raw_path = os.path.join(config.DATA_DIR, "raw_jobs.csv")
    output_path = config.OUTPUT_CSV

    df_raw = load_raw(raw_path)
    df_clean = process(df_raw)

    os.makedirs(config.DATA_DIR, exist_ok=True)
    df_clean.to_csv(output_path, index=False, encoding="utf-8")

    log.info(
        "=== Processing Complete ===\n"
        "  Output:       %s\n"
        "  Final rows:   %d\n"
        "  Columns:      %s",
        output_path,
        len(df_clean),
        list(df_clean.columns),
    )

    # Quick summary stats
    print("\n--- Dataset Summary ---")
    print(f"Total jobs       : {len(df_clean):,}")
    print(f"Countries        : {df_clean['country'].nunique()}")
    print(f"Sources          : {df_clean['source'].value_counts().to_dict()}")
    print(f"Experience levels: {df_clean['experience_level'].value_counts().to_dict()}")
    print(f"Remote types     : {df_clean['remote_type'].value_counts().to_dict()}")
    salary_df = df_clean["salary_min"].dropna()
    if not salary_df.empty:
        print(
            f"Salary (USD) min : ${salary_df.min():,.0f}  "
            f"max : ${df_clean['salary_max'].dropna().max():,.0f}  "
            f"median : ${salary_df.median():,.0f}"
        )


if __name__ == "__main__":
    main()
