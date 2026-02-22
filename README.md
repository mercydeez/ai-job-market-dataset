# AI Job Market Global Dataset

A real-time dataset of AI and Machine Learning job postings collected from two
free public APIs — **Adzuna** and **USAJobs** — covering five countries.

The dataset is designed for EDA, salary trend analysis, skills demand research,
and NLP projects on job descriptions.

---

## Dataset Description

| Property | Value |
|---|---|
| Format | CSV, UTF-8 |
| Update frequency | On-demand (re-run `collect_data.py`) |
| Countries covered | United States, United Kingdom, Canada, Australia, Germany |
| Data sources | Adzuna API, USAJobs (US Government) |
| Primary focus | AI / ML / Data Science roles |

---

## Column Descriptions

| Column | Type | Description |
|---|---|---|
| `job_title` | string | Exact job title as listed by the employer |
| `company` | string | Hiring company or government agency name |
| `country` | string | Country where the position is located |
| `city` | string | City or region within the country |
| `salary_min` | float | Minimum annual salary converted to USD (NaN if not provided) |
| `salary_max` | float | Maximum annual salary converted to USD (NaN if not provided) |
| `currency` | string | Always `USD` after normalisation |
| `remote_type` | string | `Remote`, `Hybrid`, `Onsite`, or `Unspecified` |
| `experience_level` | string | `Junior`, `Mid-level`, `Senior`, `Lead`, or `Management` |
| `required_skills` | string | Comma-separated list of AI/ML skills detected in the description |
| `posted_date` | date | Date the job was posted (ISO 8601, e.g. `2025-01-15`) |
| `source` | string | API source: `Adzuna` or `USAJobs` |
| `job_description` | string | Full description or qualification summary |

---

## Data Sources & Collection Methodology

### 1. Adzuna API
- **URL**: https://developer.adzuna.com
- **Coverage**: United States, United Kingdom, Canada, Australia, Germany
- **Search terms**: AI Engineer, Machine Learning Engineer, Data Scientist,
  LLM Engineer, Prompt Engineer, MLOps, Computer Vision Engineer, NLP Engineer,
  AI Researcher
- **Pages per query**: Up to 4 pages × 50 results = up to 200 results per
  search term / country combination
- **Authentication**: Free API key (App ID + App Key)

### 2. USAJobs API (US Government)
- **URL**: https://data.usajobs.gov/api/search
- **Coverage**: United States federal government positions only
- **Search terms**: Artificial Intelligence, Machine Learning, Data Scientist
- **Authentication**: None — only a valid `User-Agent` email header required

### Processing Pipeline
1. All raw records are merged into a single DataFrame.
2. Skills are extracted via regex keyword matching against 24 AI/ML technologies.
3. Experience level is inferred from job title and description keywords.
4. Remote work arrangement is inferred from description keywords.
5. Salaries are converted to annual USD using fixed exchange rates.
6. Duplicates are removed based on `(job_title, company, city)`.
7. Rows with missing or empty `job_title` are dropped.

---

## Project Structure

```
kaggle-ai-jobs/
├── collect_data.py         # Fetches live job postings from APIs
├── process_data.py         # Cleans, enriches, and deduplicates data
├── config.py               # API credentials and settings (reads .env)
├── eda_notebook.ipynb      # EDA notebook with 8 Plotly visualisations
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── .env.example            # Template for credentials
├── collection_log.json     # Auto-generated run log
└── data/
    ├── raw_jobs.csv        # Raw collected data (intermediate)
    └── ai_jobs_global.csv  # Final cleaned dataset
```

---

## How to Update the Dataset

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure API credentials
```bash
cp .env.example .env
# Open .env and fill in your Adzuna App ID and App Key
# Set USAJOBS_USER_AGENT to your email address
```

### 3. Collect fresh data
```bash
python collect_data.py
```

This will:
- Query all configured countries and search terms
- Print progress: `Fetching 'AI Engineer' from US... 42 jobs found`
- Save raw data to `data/raw_jobs.csv`
- Write a run summary to `collection_log.json`

### 4. Process and clean
```bash
python process_data.py
```

This produces `data/ai_jobs_global.csv` — the final dataset.

### 5. Explore (optional)
Open `eda_notebook.ipynb` in JupyterLab or VS Code to run the EDA.

---

## Suggested Use Cases

| Use Case | Description |
|---|---|
| **EDA & Visualisation** | Explore salary trends, top hiring countries, and demand by skill |
| **Salary Prediction** | Build regression models to predict salary from title, skills, and country |
| **NLP on Job Descriptions** | Topic modelling, keyword extraction, or text classification |
| **Skill Trend Analysis** | Track which technologies are growing in job demand over time |
| **Remote Work Analysis** | Study the prevalence of remote roles by country and seniority |
| **Job Recommendation** | Build a simple content-based recommender using skills and titles |

---

## Limitations

- **Exchange rates are static**: Currency conversions use fixed rates set in
  `config.py`. Real exchange rates fluctuate; recalculate if precision is needed.
- **Salary coverage is sparse**: Many job postings do not include salary details.
  Salary statistics should be interpreted with this in mind.
- **Experience level is heuristic**: Detection relies on keywords in titles and
  descriptions and may misclassify edge cases.
- **Skill detection is keyword-based**: The regex approach may miss domain
  abbreviations or spelling variations (e.g. `sklearn` vs `Scikit-learn`).
- **Adzuna free tier rate limits**: The free plan allows limited requests per
  day; the script includes rate limiting to stay within quotas.
- **USAJobs is US government only**: This source exclusively represents federal
  positions and does not reflect the broader US private sector.
- **Snapshot in time**: Each run captures a point-in-time snapshot. Job
  postings expire and new ones emerge constantly.
- **No historical backfill**: The APIs only return currently active postings;
  historical trend analysis is limited to the accumulation of repeated runs.

---

## License

Data sourced from:
- Adzuna API — subject to [Adzuna Terms of Service](https://www.adzuna.com/terms-and-conditions)
- USAJobs — US government public data, no restrictions

Code in this repository is released under the [MIT License](LICENSE).
