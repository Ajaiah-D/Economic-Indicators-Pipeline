# Economic Indicators Data Engineering Pipeline

A production-style end-to-end pipeline that ingests live macroeconomic data from
the Federal Reserve Economic Data (FRED) API, orchestrates it with Apache Airflow,
transforms it with PySpark on Databricks, models it with dbt, and surfaces insights
in a Streamlit dashboard.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRED API (St. Louis Fed)                    │
│  CPI · Unemployment · GDP · Fed Funds Rate · Housing Starts · Sent. │
└───────────────────────────┬─────────────────────────────────────────┘
                            │  fredapi (Python)
                            ▼
┌───────────────────────────────────────────────────────────────────────┐
│                    Ingestion  (ingestion/fetch_fred.py)               │
│  • Authenticates with FRED API key                                    │
│  • Fetches each series as a timestamped DataFrame                     │
│  • Writes CSV to s3://<bucket>/raw/<label>/<date>/<series_id>.csv    │
└───────────────────────────┬───────────────────────────────────────────┘
                            │  boto3
                            ▼
                  ┌─────────────────┐
                  │   AWS S3 (raw)  │
                  └────────┬────────┘
                           │  Airflow schedules daily
                           ▼
┌───────────────────────────────────────────────────────────────────────┐
│             Apache Airflow DAG  (dags/fred_ingestion_dag.py)         │
│  • TaskFlow API (@dag / @task)                                        │
│  • One fetch + one write task per indicator (6 branches)             │
│  • Daily schedule · retry logic · email-on-failure stubs             │
└───────────────────────────┬───────────────────────────────────────────┘
                            │  triggers PySpark job
                            ▼
┌───────────────────────────────────────────────────────────────────────┐
│         PySpark / Databricks  (spark/transform_indicators.py)        │
│  • Reads raw CSVs from S3                                             │
│  • Casts types, computes MoM % change, 3-month rolling avg           │
│  • Full outer joins all six indicators by date into wide table        │
│  • Writes Parquet to s3://<bucket>/processed/economic_indicators/    │
└───────────────────────────┬───────────────────────────────────────────┘
                            │  processed Parquet
                            ▼
┌───────────────────────────────────────────────────────────────────────┐
│                    dbt  (dbt/)                                        │
│  staging/  stg_fred_indicators      – type casting & column contract │
│  intermediate/ int_indicator_trends – trend flags & signal scoring   │
│  marts/    economic_dashboard       – final table (materialized)     │
└───────────────────────────┬───────────────────────────────────────────┘
                            │  mart Parquet / Snowflake table
                            ▼
┌───────────────────────────────────────────────────────────────────────┐
│               Streamlit Dashboard  (dashboard/app.py)                │
│  • Date-range slider, multi-indicator selector                        │
│  • KPI cards with MoM delta                                           │
│  • Line charts: raw / MoM % / 3-month rolling avg                    │
│  • Signal score gauge + active flag list                              │
│  • Flag history heatmap                                               │
└───────────────────────────────────────────────────────────────────────┘
```

---

## FRED Indicators

| Series ID   | Label              | Frequency | Units                    |
|-------------|--------------------|-----------|--------------------------|
| CPIAUCSL    | CPI                | Monthly   | Index (1982-84 = 100)    |
| UNRATE      | Unemployment Rate  | Monthly   | Percent                  |
| GDP         | GDP                | Quarterly | Billions of USD          |
| FEDFUNDS    | Fed Funds Rate     | Monthly   | Percent                  |
| HOUST       | Housing Starts     | Monthly   | Thousands of units       |
| UMCSENT     | Consumer Sentiment | Monthly   | Index                    |

---

## Project Structure

```
fred-pipeline/
├── dags/
│   └── fred_ingestion_dag.py      Airflow DAG (TaskFlow API)
├── ingestion/
│   └── fetch_fred.py              FRED → S3 ingestion
├── spark/
│   └── transform_indicators.py   PySpark feature engineering
├── dbt/
│   ├── dbt_project.yml
│   └── models/
│       ├── staging/
│       │   └── stg_fred_indicators.sql
│       ├── intermediate/
│       │   └── int_indicator_trends.sql
│       └── marts/
│           └── economic_dashboard.sql
├── dashboard/
│   └── app.py                     Streamlit dashboard
├── .env.example
├── requirements.txt
└── README.md
```

---

## Setup

### Prerequisites

- Python 3.11+
- An AWS account with an S3 bucket and an IAM user with `s3:GetObject` / `s3:PutObject`
- A FRED API key (free at [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html))
- Databricks Community Edition account (for the Spark step)

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd fred-pipeline
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp .env.example .env
# Edit .env and fill in FRED_API_KEY, AWS_*, etc.
```

---

## How to Run Each Stage

### Stage 1: Ingest from FRED to S3

```bash
python ingestion/fetch_fred.py
```

Fetches all six series and uploads timestamped CSVs to
`s3://<AWS_BUCKET_NAME>/raw/`.

---

### Stage 2: Run the Airflow DAG locally

```bash
# Initialise the Airflow SQLite DB and start the web server + scheduler
export AIRFLOW_HOME=$(pwd)/airflow-home
airflow standalone

# In a second terminal, trigger the DAG manually
airflow dags trigger fred_economic_ingestion

# Watch progress
airflow dags list-runs -d fred_economic_ingestion
```

The web UI is available at `http://localhost:8080` (default user: `admin`).

---

### Stage 3: PySpark transformation on Databricks

1. Log in to [Databricks Community Edition](https://community.cloud.databricks.com).
2. Create a cluster (any runtime >= 13.3 LTS).
3. Upload `spark/transform_indicators.py` to your workspace.
4. Set the following environment variables in the cluster configuration
   (Cluster -> Edit -> Environment Variables):

   ```
   AWS_ACCESS_KEY_ID=...
   AWS_SECRET_ACCESS_KEY=...
   AWS_BUCKET_NAME=...
   AWS_REGION=us-east-1
   ```

5. Create a notebook, attach it to the cluster, and run:

   ```python
   %run ./transform_indicators
   ```

   Or submit via `spark-submit` for local testing:

   ```bash
   spark-submit spark/transform_indicators.py
   ```

Output is written to `s3://<bucket>/processed/economic_indicators/` as
Snappy-compressed Parquet.

---

### Stage 4: Run dbt models

For **local testing with dbt-duckdb**, add a profile to `~/.dbt/profiles.yml`:

```yaml
fred_pipeline:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: dbt/target/fred_pipeline.duckdb
      extensions:
        - httpfs
      settings:
        s3_access_key_id: "{{ env_var('AWS_ACCESS_KEY_ID') }}"
        s3_secret_access_key: "{{ env_var('AWS_SECRET_ACCESS_KEY') }}"
        s3_region: "{{ env_var('AWS_REGION', 'us-east-1') }}"
```

Then run:

```bash
cd dbt
dbt deps
dbt run
dbt test
```

For **Databricks**, swap the profile to `dbt-spark` and point it at your cluster.

---

### Stage 5: Launch the Streamlit dashboard

```bash
streamlit run dashboard/app.py
```

The dashboard loads data in this priority order:
1. `dbt/target/economic_dashboard.parquet` (fastest, local dbt-duckdb output)
2. `data/economic_dashboard.parquet` (the committed snapshot, see below)
3. S3 Parquet (via boto3; set `AWS_*` env vars)
4. Synthetic demo data (no backend required, great for UI previews)

---

### Automated daily refresh (GitHub Actions)

`.github/workflows/refresh_data.yml` runs the full pipeline (ingest, transform, dbt run,
export) on a schedule and commits the result back to the repo at
`data/economic_dashboard.parquet` and `data/last_updated.json`, only if the data actually
changed. This is what keeps a deployed dashboard (e.g. Streamlit Community Cloud) showing
current data without needing AWS credentials at deploy time, since it just reads the
committed snapshot.

It runs daily at 12:00 UTC and can also be triggered manually from the Actions tab
(`workflow_dispatch`).

**One-time setup:** add these as repository secrets (Settings -> Secrets and variables ->
Actions -> New repository secret). The workflow uses the default `GITHUB_TOKEN` to push,
no separate token needed for that part:
- `FRED_API_KEY`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_BUCKET_NAME`
- `AWS_REGION`

---

## Key Findings & Economic Signal Logic

The pipeline computes a **signal score (0-6)** by counting how many of the
following stress conditions are simultaneously active on any given month:

| Flag                      | Condition                                         |
|---------------------------|---------------------------------------------------|
| Unemployment Rising       | 3-month avg > 3-month avg from 3 months prior     |
| GDP Contracting           | GDP MoM % change < 0                             |
| Inflation Elevated        | CPI 12-month change > 3%                         |
| Fed Rate Elevated         | Effective funds rate > 4%                        |
| Housing Starts Declining  | Housing starts MoM % change < 0                 |
| Consumer Sentiment Falling| Sentiment MoM % change < 0                      |

A score >= 3 triggers the **Recession Watch** flag, a heuristic inspired by
the simultaneous deterioration seen ahead of the 2008 and 2020 downturns.

> **Placeholder for extended analysis:** After connecting live FRED data, add
> a write-up here describing which signals fired in the most recent 12 months,
> how the current signal score compares to historical recessions, and any
> indicator divergences worth monitoring (e.g., persistent inflation while
> unemployment remains low, a stagflation setup).

---

## Tech Stack

| Layer         | Technology                                    |
|---------------|-----------------------------------------------|
| Ingestion     | Python, fredapi, boto3, python-dotenv         |
| Orchestration | Apache Airflow 2.9 (TaskFlow API)             |
| Processing    | PySpark 3.5, Databricks Community Edition     |
| Modeling      | dbt-core, dbt-duckdb (dev) / dbt-spark (prod) |
| Storage       | AWS S3 (raw CSV + processed Parquet)          |
| Visualization | Streamlit, Plotly                             |
