"""
config.py
---------
Central configuration for the AI Job Market data collection project.
All sensitive credentials are loaded from a .env file via python-dotenv.

Usage:
    Copy .env.example to .env and fill in your API keys before running.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file in the project root
load_dotenv()

# ---------------------------------------------------------------------------
# Adzuna API credentials
# Sign up at: https://developer.adzuna.com
# ---------------------------------------------------------------------------
ADZUNA_APP_ID: str = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY: str = os.getenv("ADZUNA_APP_KEY", "")
ADZUNA_BASE_URL: str = "https://api.adzuna.com/v1/api/jobs"

# ---------------------------------------------------------------------------
# USAJobs API configuration
# Register for a free key at: https://developer.usajobs.gov/APIRequest/Index
# ---------------------------------------------------------------------------
USAJOBS_BASE_URL: str = "https://data.usajobs.gov/api/search"
USAJOBS_USER_AGENT: str = os.getenv("USAJOBS_USER_AGENT", "user@example.com")
USAJOBS_AUTH_KEY: str = os.getenv("USAJOBS_AUTH_KEY", "")

# ---------------------------------------------------------------------------
# Countries to query via Adzuna
# ---------------------------------------------------------------------------
ADZUNA_COUNTRIES: list[str] = ["us", "gb", "ca", "au", "de"]

# Human-readable country name map (Adzuna code → display name)
COUNTRY_NAME_MAP: dict[str, str] = {
    "us": "United States",
    "gb": "United Kingdom",
    "ca": "Canada",
    "au": "Australia",
    "de": "Germany",
}

# ---------------------------------------------------------------------------
# Search keywords
# ---------------------------------------------------------------------------
ADZUNA_SEARCH_TERMS: list[str] = [
    "AI Engineer",
    "Machine Learning Engineer",
    "Data Scientist",
    "LLM Engineer",
    "Prompt Engineer",
    "MLOps",
    "Computer Vision Engineer",
    "NLP Engineer",
    "AI Researcher",
]

USAJOBS_SEARCH_TERMS: list[str] = [
    "Artificial Intelligence",
    "Machine Learning",
    "Data Scientist",
]

# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------
ADZUNA_RESULTS_PER_PAGE: int = 50   # Max allowed by Adzuna free tier
ADZUNA_MAX_PAGES: int = 4           # Up to 200 results per search term / country
USAJOBS_MAX_PAGES: int = 4          # Up to 200 results per USAJobs search term

# ---------------------------------------------------------------------------
# Retry / rate-limit settings
# ---------------------------------------------------------------------------
RETRY_ATTEMPTS: int = 3
RETRY_WAIT_SECONDS: int = 2       # Minimum wait; retries use exponential backoff
RATE_LIMIT_SLEEP: float = 1.0     # Seconds between every API call (success or error)

# ---------------------------------------------------------------------------
# Currency conversion rates → USD
# ---------------------------------------------------------------------------
CURRENCY_TO_USD: dict[str, float] = {
    "GBP": 1.27,
    "CAD": 0.74,
    "AUD": 0.65,
    "EUR": 1.08,
    "USD": 1.00,
}

# Default currency per Adzuna country code
COUNTRY_CURRENCY: dict[str, str] = {
    "us": "USD",
    "gb": "GBP",
    "ca": "CAD",
    "au": "AUD",
    "de": "EUR",
}

# ---------------------------------------------------------------------------
# Skill keywords to extract from job descriptions
# ---------------------------------------------------------------------------
SKILL_KEYWORDS: list[str] = [
    "Python", "R", "SQL", "PyTorch", "TensorFlow", "Keras", "Scikit-learn",
    "HuggingFace", "LangChain", "OpenAI", "AWS", "GCP", "Azure", "Docker",
    "Kubernetes", "Spark", "Hadoop", "NLP", "Computer Vision", "RAG",
    "Fine-tuning", "Transformers", "MLflow", "Airflow",
]

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------
DATA_DIR: str = "data"
OUTPUT_CSV: str = os.path.join(DATA_DIR, "ai_jobs_global.csv")
COLLECTION_LOG: str = "collection_log.json"
