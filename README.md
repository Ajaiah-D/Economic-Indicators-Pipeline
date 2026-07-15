# Economic Indicators Pipeline

An end-to-end data pipeline that pulls six macroeconomic indicators from the
Federal Reserve (FRED), moves them through ingestion, orchestration, and
transformation, models them with dbt, and serves the result in a Streamlit
dashboard with a simple recession-risk signal.

**Live dashboard:** https://ajaiah-d-economic-indicators-pipeline-dashboardapp-d8tih5.streamlit.app/

---

## Architecture

1. **Ingestion** (`ingestion/fetch_fred.py`) pulls each of the six series from the FRED API and writes timestamped CSVs to S3, partitioned by indicator and date.
2. **Orchestration** (`dags/fred_ingestion_dag.py`) runs that ingestion on a daily Airflow DAG (TaskFlow API), one fetch/write task pair per indicator, with retries and exponential backoff.
3. **Transform** (`spark/transform_indicators.py` or `spark/transform_indicators_local.py`) reads the raw CSVs, computes month-over-month % change and a 3-month rolling average per indicator, joins all six into one wide table by date, and writes it back to S3 as Parquet.
4. **Modeling** (`dbt/`) builds three layers on top of that Parquet file with dbt-duckdb: a staging view (type casting), an intermediate view (six binary stress flags + a composite signal score), and a materialized marts table.
5. **Dashboard** (`dashboard/app.py`) is Streamlit + Plotly: KPI tiles, a per-indicator trends view, the recession-risk signal, and a flag history heatmap.
6. **Refresh** (`.github/workflows/refresh_data.yml`) runs the whole chain daily and commits a small snapshot back to the repo, so the deployed dashboard always has current data without needing any credentials at deploy time.

## FRED Indicators

| Series ID   | Label              | Frequency | Units                    |
|-------------|--------------------|-----------|--------------------------|
| CPIAUCSL    | CPI                | Monthly   | Index (1982-84 = 100)    |
| UNRATE      | Unemployment Rate  | Monthly   | Percent                  |
| GDP         | GDP                | Quarterly | Billions of USD          |
| FEDFUNDS    | Fed Funds Rate     | Monthly   | Percent                  |
| HOUST       | Housing Starts     | Monthly   | Thousands of units       |
| UMCSENT     | Consumer Sentiment | Monthly   | Index                    |

## Project Structure

```
Economic-Indicators-Pipeline/
├── ingestion/
│   └── fetch_fred.py                  FRED -> S3 ingestion
├── dags/
│   └── fred_ingestion_dag.py          Airflow DAG (TaskFlow API)
├── spark/
│   ├── transform_indicators.py        PySpark version, for a Databricks cluster
│   └── transform_indicators_local.py  pandas equivalent, used by the daily refresh
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml
│   └── models/
│       ├── staging/stg_fred_indicators.sql
│       ├── intermediate/int_indicator_trends.sql
│       └── marts/economic_dashboard.sql
├── dashboard/
│   └── app.py                         Streamlit dashboard
├── scripts/
│   └── export_dashboard_snapshot.py   dbt output -> committed Parquet snapshot
├── data/
│   ├── economic_dashboard.parquet     committed snapshot, refreshed daily
│   └── last_updated.json
├── .github/workflows/
│   └── refresh_data.yml               daily ingest -> transform -> dbt -> snapshot
├── .env.example
├── requirements.txt                   dashboard runtime only
└── requirements-pipeline.txt          full pipeline (Airflow, PySpark, dbt)
```

## Setup

### Prerequisites

- Python 3.12 (Airflow and PySpark don't support the newest Python releases)
- An AWS account with an S3 bucket and an IAM user scoped to that bucket (`s3:GetObject` / `s3:PutObject` / `s3:ListBucket`)
- A FRED API key (free at [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html))

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd Economic-Indicators-Pipeline
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-pipeline.txt
```

`requirements.txt` is the slim runtime Streamlit Community Cloud installs for
the dashboard alone, deliberately skipping Airflow, PySpark, and dbt so the
hosted build stays fast. Use `requirements-pipeline.txt` for full local
development.

### 2. Configure credentials

```bash
cp .env.example .env
# fill in FRED_API_KEY, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_BUCKET_NAME, AWS_REGION
```

## Running each stage

### 1. Ingest from FRED to S3

```bash
python ingestion/fetch_fred.py
```

Fetches all six series and uploads timestamped CSVs to `s3://<AWS_BUCKET_NAME>/raw/`.

### 2. Run the Airflow DAG locally

Apache Airflow doesn't run natively on Windows; use WSL2 or a Linux/Mac shell.

```bash
export AIRFLOW_HOME=$(pwd)/airflow-home
airflow standalone

# in a second terminal
airflow dags trigger fred_economic_ingestion
airflow dags list-runs -d fred_economic_ingestion
```

The web UI is at `http://localhost:8080` (default user: `admin`).

### 3. Transform: local pandas or PySpark on Databricks

The daily refresh workflow uses the local pandas version, since the dataset
is under a thousand rows total and a Spark cluster isn't buying anything at
this scale:

```bash
python spark/transform_indicators_local.py
```

`spark/transform_indicators.py` is the PySpark equivalent, written for a
larger dataset running on an actual Databricks cluster (Databricks Free
Edition dropped support for all-purpose clusters, so it now needs a Unity
Catalog external location to reach S3 rather than a simple access key).
Either way, the output lands at `s3://<bucket>/processed/economic_indicators/`.

### 4. Run dbt models

dbt reads the S3 Parquet directly through dbt-duckdb's `httpfs` extension.
`dbt/profiles.yml` is already checked in and only references environment
variables, so no manual profile setup is needed:

```bash
cd dbt
dbt run
dbt test
```

### 5. Export the dashboard snapshot

```bash
python scripts/export_dashboard_snapshot.py
```

Copies the dbt marts table to `data/economic_dashboard.parquet` and writes
`data/last_updated.json` (timestamp, row count, date range). This is the
file a deployed dashboard actually reads.

### 6. Launch the dashboard

```bash
streamlit run dashboard/app.py
```

Data loads in this order: a local dbt build, then the committed snapshot,
then S3 (if `AWS_*` env vars are set), then synthetic demo data as a last
resort so the UI is still browsable with zero setup.

## Automated daily refresh

`.github/workflows/refresh_data.yml` runs steps 1, 3, 4, and 5 above on a
schedule (12:00 UTC daily, plus manual `workflow_dispatch`) and commits the
result back to the repo, only if the data actually changed. This is what
keeps the deployed dashboard current without it ever needing AWS credentials
at deploy time; it just reads the committed snapshot.

**One-time setup:** add these as repository secrets (Settings → Secrets and
variables → Actions). The workflow pushes with the default `GITHUB_TOKEN`,
no extra token needed for that part:

- `FRED_API_KEY`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_BUCKET_NAME`
- `AWS_REGION`

## Recession-risk signal

Six binary stress flags are checked each month, and the signal score is just
how many are active at once, 0-6:

| Flag                        | Condition                                                  |
|------------------------------|--------------------------------------------------------------|
| Unemployment rising          | 3-month avg > 3-month avg from 3 months prior                |
| GDP contracting              | GDP quarter-over-quarter change < 0                          |
| Inflation elevated           | CPI 12-month change > 3%                                     |
| Fed rate elevated            | Effective funds rate > its own trailing 3-year average + 1pt |
| Housing starts declining     | 3-month avg < 3-month avg from 3 months prior                |
| Consumer sentiment falling   | 3-month avg < 3-month avg from 3 months prior                |

A score of 3 or more trips the **Recession Watch** flag.

### Backtest

All six indicators only overlap from 1959 onward, so that's the window this
was actually checked against, not just anecdotally citing a couple of recent
recessions. Against all 9 NBER-recognized recessions since 1959:

- **Catches all 9** (score reached 3+ within 6 months of every recession's official start).
- The housing/sentiment flags originally used a single month's up-or-down move, and the fed-funds
  flag used a fixed ">4%" regardless of era, which doesn't mean the same thing in 1981 (rates
  above 10%) as it does in 2015 (rates near zero). On those original thresholds, the signal fired
  3+ in about 45% of all months since 1959, most of them nowhere near a real recession. Smoothing
  those two flags to a 3-month trend and making the fed-funds flag relative to its own trailing
  average (both above) cut that to about 34% of months, with the same 9/9 recall.
- Tried adding a persistence requirement (score has to stay 3+ for 2 consecutive months to count)
  on top of that: it cuts false positives further but misses the 2020 recession, which was over in
  two months and never got the chance to persist. Left out for that reason.

Even at 34%, this is a broad stress gauge, not a precise predictor: about one in three flagged
months turns out to be near an actual recession. Useful as one input among others, not a signal
to act on alone.

## Tech Stack

| Layer         | Technology                                       |
|---------------|---------------------------------------------------|
| Ingestion     | Python, fredapi, boto3                            |
| Orchestration | Apache Airflow 2.9 (TaskFlow API)                 |
| Transform     | pandas (default) or PySpark 3.5 on Databricks     |
| Modeling      | dbt-core + dbt-duckdb                             |
| Storage       | AWS S3 (raw CSV + processed Parquet)              |
| Dashboard     | Streamlit, Plotly                                 |
| Automation    | GitHub Actions (daily refresh)                    |
