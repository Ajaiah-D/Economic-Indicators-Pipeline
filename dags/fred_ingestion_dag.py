"""
Daily ingestion DAG for FRED economic indicators.

Six indicator branches (fetch -> upload) all fan into a single log task.
FRED publishes most series monthly, but running daily means we pick up
any intra-month revisions without manual reruns.

Local dev:
    export AIRFLOW_HOME=$(pwd)/airflow-home
    airflow standalone
    airflow dags trigger fred_economic_ingestion
"""

import logging
from datetime import datetime, timedelta

from airflow.decorators import dag, task

INDICATORS = {
    "CPIAUCSL": "cpi",
    "UNRATE": "unemployment_rate",
    "U6RATE": "u6_rate",
    "GDP": "gdp",
    "FEDFUNDS": "fed_funds_rate",
    "HOUST": "housing_starts",
    "UMCSENT": "consumer_sentiment",
}

DEFAULT_ARGS = {
    "owner": "data-eng",
    "depends_on_past": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=60),
    "email": ["data-eng@example.com"],
    "email_on_failure": True,
    "email_on_retry": False,
}


@dag(
    dag_id="fred_economic_ingestion",
    description="Ingest FRED macroeconomic series to S3 daily",
    schedule="0 6 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["fred", "ingestion", "economics"],
)
def fred_economic_ingestion():

    @task()
    def fetch_indicator(series_id: str, label: str, run_date: str) -> dict:
        import os
        import sys

        # project root needs to be on the path when running under airflow standalone
        project_root = os.path.join(os.path.dirname(__file__), "..")
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        from ingestion.fetch_fred import fetch_series

        df = fetch_series(series_id, label)
        return {
            "series_id": series_id,
            "label": label,
            "run_date": run_date,
            "data_json": df.to_json(orient="records"),
            "rows": len(df),
        }

    @task()
    def write_to_s3(payload: dict) -> dict:
        import io
        import os
        import sys
        from datetime import date

        import pandas as pd

        project_root = os.path.join(os.path.dirname(__file__), "..")
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        from ingestion.fetch_fred import upload_to_s3

        df = pd.read_json(io.StringIO(payload["data_json"]), orient="records")
        run_date = date.fromisoformat(payload["run_date"])
        key = upload_to_s3(df, payload["series_id"], payload["label"], run_date)
        # drop data_json before returning so XCom stays small
        return {**payload, "s3_key": key, "data_json": None}

    @task()
    def log_result(results: list[dict]) -> None:
        logger = logging.getLogger("airflow.task")
        succeeded = [r for r in results if r.get("s3_key")]
        failed = [r for r in results if not r.get("s3_key")]
        logger.info("FRED ingestion complete -- %d ok, %d failed", len(succeeded), len(failed))
        if failed:
            logger.warning("Failed series: %s", [r["series_id"] for r in failed])

    run_date_str = "{{ ds }}"

    upload_results = []
    for series_id, label in INDICATORS.items():
        fetched = fetch_indicator(series_id, label, run_date_str)
        uploaded = write_to_s3(fetched)
        upload_results.append(uploaded)

    log_result(upload_results)


fred_economic_ingestion()
