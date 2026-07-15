import io
import json
import logging
import os
from datetime import date, datetime

import boto3
import pandas as pd
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from fredapi import Fred

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

INDICATORS = {
    "CPIAUCSL": "cpi",
    "UNRATE": "unemployment_rate",
    "GDP": "gdp",
    "FEDFUNDS": "fed_funds_rate",
    "HOUST": "housing_starts",
    "UMCSENT": "consumer_sentiment",
    "GS10": "treasury_10y",
    "TB3MS": "treasury_3m",
}


def _fred_client() -> Fred:
    return Fred(api_key=os.environ["FRED_API_KEY"])


def _s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )


def _s3_key(series_id: str, label: str, run_date: date) -> str:
    return f"raw/{label}/{run_date.isoformat()}/{series_id}.csv"


def fetch_series(series_id: str, label: str) -> pd.DataFrame:
    fred = _fred_client()
    data = fred.get_series(series_id)
    df = (
        data.rename_axis("date")
        .reset_index()
        .rename(columns={0: "value"})
        .assign(series_id=series_id, label=label)
    )
    df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    logger.info("Fetched %d rows for %s (%s)", len(df), series_id, label)
    return df


def upload_to_s3(df: pd.DataFrame, series_id: str, label: str, run_date: date) -> str:
    key = _s3_key(series_id, label, run_date)
    bucket = os.environ["AWS_BUCKET_NAME"]
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    s3 = _s3_client()
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=buf.getvalue())
        logger.info("Uploaded s3://%s/%s", bucket, key)
    except ClientError as exc:
        logger.error("S3 upload failed for %s: %s", series_id, exc)
        raise
    return key


def fetch_and_upload(series_id: str, label: str, run_date: date | None = None) -> dict:
    if run_date is None:
        run_date = datetime.utcnow().date()
    df = fetch_series(series_id, label)
    key = upload_to_s3(df, series_id, label, run_date)
    return {
        "series_id": series_id,
        "label": label,
        "rows": len(df),
        "s3_key": key,
        "run_date": run_date.isoformat(),
    }


def run_all(run_date: date | None = None) -> list[dict]:
    results, errors = [], []
    for series_id, label in INDICATORS.items():
        try:
            results.append(fetch_and_upload(series_id, label, run_date))
        except Exception as exc:
            logger.error("Failed to process %s: %s", series_id, exc)
            errors.append({"series_id": series_id, "error": str(exc)})

    logger.info("Run complete -- %d succeeded, %d failed", len(results), len(errors))
    print(json.dumps({"successes": results, "failures": errors}, indent=2))
    return results


if __name__ == "__main__":
    run_all()
