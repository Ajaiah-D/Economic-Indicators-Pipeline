# Economic Indicators Pipeline

An end-to-end data pipeline over 160+ Federal Reserve (FRED/ALFRED) data
series: national macro indicators with a backtested recession-risk signal
and an auto-written monthly briefing, state-level unemployment, house
prices, and income for all 50 states + DC, and point-in-time vintage data
showing how first-print numbers were later revised. Ingestion,
orchestration, and transformation feed dbt models, and a three-page
Streamlit dashboard serves the result, refreshed daily.

**Live dashboard:** https://ajaiah-d-economic-indicators-pipeline-dashboardapp-d8tih5.streamlit.app/

---

## Architecture

1. **Ingestion** (`ingestion/`) pulls from the FRED API and writes timestamped CSVs to S3: `fetch_fred.py` for the eight national series, `fetch_fred_states.py` for ~150 state-level series (rate-limited batch), and `fetch_fred_vintages.py` for ALFRED vintage data -- every value each series has ever published.
2. **Orchestration** (`dags/fred_ingestion_dag.py`) runs the national ingestion on a daily Airflow DAG (TaskFlow API), one fetch/write task pair per indicator, with retries and exponential backoff.
3. **Transform** (`spark/`) reads the raw CSVs and writes processed Parquet back to S3: national wide table with MoM % change, 3-month rolling averages, and the 10Y-3M Treasury spread; a long state table with per-state YoY changes computed at each indicator's native frequency; and a long vintage table keyed by (series, observation date, release date).
4. **Modeling** (`dbt/`) builds staging views and materialized marts with dbt-duckdb: the national mart adds seven binary stress flags + a composite signal score, the state mart adds per-date ranks across the 51-state field, and the vintage mart adds first-print / latest-revision window columns.
5. **Dashboard** (`dashboard/`) is a multi-page Streamlit + Plotly app -- see "Dashboard pages" below.
6. **Refresh** (`.github/workflows/refresh_data.yml`) runs the whole chain daily and commits small snapshots back to the repo, so the deployed dashboard always has current data without needing any credentials at deploy time.

## Dashboard pages

- **National overview**: KPI tiles, per-indicator trends, the recession-risk
  signal with flag-history heatmap, and a **monthly briefing written
  automatically from the data**: it diffs the latest complete month against
  the prior one and scans each series' full history so it can say "housing
  starts fell 15%, the sharpest monthly drop since 2024, activating a stress
  flag" instead of just showing numbers.
- **State by state**: unemployment (monthly), FHFA house-price growth
  (quarterly), and per-capita income (annual) for all 50 states + DC; each
  state ranked against the field, charted against the U.S., and mapped on a
  choropleth.
- **Data revisions**: built on ALFRED vintage data. GDP growth as first
  reported vs today's estimate (computed within vintages, so benchmark
  rebasings of the level can't distort it), and a "time machine" that
  reconstructs unemployment, housing starts, or payrolls exactly as they
  looked on any chosen date -- e.g. the economy as visible in September 2008
  vs what we now know was happening.

## FRED Indicators

| Series ID   | Label                | Frequency | Units                    |
|-------------|----------------------|-----------|--------------------------|
| CPIAUCSL    | CPI                  | Monthly   | Index (1982-84 = 100)    |
| UNRATE      | Unemployment Rate    | Monthly   | Percent                  |
| GDP         | GDP                  | Quarterly | Billions of USD          |
| FEDFUNDS    | Fed Funds Rate       | Monthly   | Percent                  |
| HOUST       | Housing Starts       | Monthly   | Thousands of units       |
| UMCSENT     | Consumer Sentiment   | Monthly   | Index                    |
| GS10        | 10-Year Treasury     | Monthly   | Percent                  |
| TB3MS       | 3-Month Treasury     | Monthly   | Percent                  |

GS10 minus TB3MS gives the yield-curve spread used in the recession signal below.

Beyond these, the pipeline also ingests:

- **State-level** (~150 series): `{ST}UR` unemployment rate (monthly), `{ST}STHPI`
  FHFA all-transactions house price index (quarterly), and `{ST}PCPI` per-capita
  personal income (annual) for all 50 states + DC.
- **Vintages** (ALFRED): every value ever published for GDP, PAYEMS (nonfarm
  payrolls), UNRATE, and HOUST -- one row per (observation date, release date).

## Project Structure

```
Economic-Indicators-Pipeline/
├── ingestion/
│   ├── fetch_fred.py                  national series -> S3
│   ├── fetch_fred_states.py           ~150 state series -> S3 (rate-limited)
│   └── fetch_fred_vintages.py         ALFRED vintage data -> S3
├── dags/
│   └── fred_ingestion_dag.py          Airflow DAG (TaskFlow API)
├── spark/
│   ├── transform_indicators.py        PySpark version, for a Databricks cluster
│   ├── transform_indicators_local.py  pandas equivalent, used by the daily refresh
│   ├── transform_states_local.py      state long table + per-state YoY changes
│   └── transform_vintages_local.py    vintage long table (obs date x release date)
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml
│   └── models/
│       ├── staging/                   stg_fred_indicators, stg_state_indicators,
│       │                              stg_fred_vintages
│       ├── intermediate/int_indicator_trends.sql
│       └── marts/                     economic_dashboard, state_dashboard,
│                                      vintage_dashboard
├── dashboard/
│   ├── app.py                         entry point + national page + navigation
│   ├── briefing.py                    auto-written monthly briefing engine
│   ├── states_view.py                 state-by-state page
│   ├── revisions_view.py              data-revisions page
│   └── theme.py                       shared design tokens + chart helpers
├── scripts/
│   └── export_dashboard_snapshot.py   dbt marts -> committed Parquet snapshots
├── data/
│   ├── economic_dashboard.parquet     committed snapshots, refreshed daily
│   ├── state_dashboard.parquet
│   ├── vintage_dashboard.parquet
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
python ingestion/fetch_fred.py           # 8 national series
python ingestion/fetch_fred_states.py    # ~150 state series (takes ~90s, rate-limited)
python ingestion/fetch_fred_vintages.py  # ALFRED vintages for 4 series
```

Each uploads timestamped CSVs to `s3://<AWS_BUCKET_NAME>/raw/`.

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

The daily refresh workflow uses the local pandas versions, since the datasets
are tens of thousands of rows at most and a Spark cluster isn't buying
anything at this scale:

```bash
python spark/transform_indicators_local.py
python spark/transform_states_local.py
python spark/transform_vintages_local.py
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

Copies the dbt mart tables to `data/*.parquet` (national, state, vintage)
and writes `data/last_updated.json` (timestamp, row counts, date ranges).
These are the files a deployed dashboard actually reads.

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

Seven binary stress flags are checked each month, and the signal score is
just how many are active at once, 0-7:

| Flag                        | Condition                                                     |
|------------------------------|-----------------------------------------------------------------|
| Unemployment rising          | 3-month avg > 3-month avg from 3 months prior                   |
| GDP contracting              | GDP quarter-over-quarter change < 0                              |
| Inflation elevated           | CPI 12-month change > 3%                                        |
| Fed rate elevated            | Effective funds rate > its own trailing 3-year average + 1pt    |
| Housing starts declining     | 3-month avg < 3-month avg from 3 months prior                    |
| Consumer sentiment falling   | 3-month avg < 3-month avg from 3 months prior                    |
| Yield curve inverted         | 10Y minus 3M Treasury spread < -0.25pt                           |

A score of 4 or more trips the **Recession Watch** flag.

### Backtest

All indicators only overlap from 1959 onward, so that's the window this was
actually checked against, not just anecdotally citing a couple of recent
recessions. Against all 9 NBER-recognized recessions since 1959:

- **Catches all 9** (score reached 4+ within 6 months of every recession's official start,
  except two, see below).
- The original 6-flag version (no yield curve, threshold of 3) also caught all 9, but flagged
  3+ in about 34% of all months since 1959, and only 45% of those flagged months were actually
  near a real recession, roughly a coin flip.
- Adding the yield curve, the single most established recession indicator in macro, as a 7th
  flag and raising the bar to 4 of 7 cuts the flagged rate to about 18% of months and lifts
  precision to about 56%, all without losing a single recession from the backtest.
- Trade-off: 2 of the 9 recessions (1960 and 2020) only cross the 4-flag bar during the
  recession itself rather than ahead of it, both were unusually short recessions. The other
  7 still get 5-6 months of lead time, unchanged from the 6-flag version.
- Also tested: requiring the yield curve to be inverted as a hard gate (score>=3 of the
  other 6 AND yield inverted) pushes precision to ~66%, but drops recall to 7 of 9, missing
  1960 and 2020 entirely. Rejected for the same reason the persistence filter was rejected
  in the earlier version: it trades away real recessions for a cleaner-looking metric.

Even at ~56% precision, this is a broad stress gauge, not a precise predictor: a little under
half of flagged months turn out not to be near an actual recession. Useful as one input among
others, not a signal to act on alone.

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
