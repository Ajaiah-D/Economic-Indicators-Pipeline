"""
Vintage-data ingestion from ALFRED (archival FRED): every value each series
has *ever* published for every observation date, not just today's revised
numbers.

This is what makes a "what did we know and when" view possible: the GDP
print policymakers saw in September 2008 is not the number FRED shows for
Q2 2008 today. ALFRED serves those historical vintages through the same
API (fredapi's get_series_all_releases), one call per series.

Series chosen for how heavily their revisions actually matter:
GDP (benchmark revisions can flip the sign of a quarter's growth),
payrolls (monthly revisions make headlines on their own), unemployment
(annual seasonal re-estimation), and housing starts.
"""

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

VINTAGE_INDICATORS = {
    "GDP": "gdp",
    "PAYEMS": "nonfarm_payrolls",
    "UNRATE": "unemployment_rate",
    "HOUST": "housing_starts",
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


def fetch_vintages(fred: Fred, series_id: str, label: str) -> pd.DataFrame:
    """Long frame: one row per (observation date, release date, value)."""
    df = fred.get_series_all_releases(series_id)
    df = df.rename(columns={"realtime_start": "release_date"})
    df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
    df["release_date"] = pd.to_datetime(df["release_date"]).dt.date.astype(str)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.assign(series_id=series_id, label=label)[
        ["date", "release_date", "value", "series_id", "label"]
    ]
    logger.info("Fetched %d vintage rows for %s (%s)", len(df), series_id, label)
    return df


def upload_to_s3(df: pd.DataFrame, label: str, run_date: date) -> str:
    key = f"raw/vintages/{label}/{run_date.isoformat()}/{label}.csv"
    bucket = os.environ["AWS_BUCKET_NAME"]
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    try:
        _s3_client().put_object(Bucket=bucket, Key=key, Body=buf.getvalue())
        logger.info("Uploaded s3://%s/%s", bucket, key)
    except ClientError as exc:
        logger.error("S3 upload failed for %s: %s", label, exc)
        raise
    return key


def run_all(run_date: date | None = None) -> list[dict]:
    if run_date is None:
        run_date = datetime.utcnow().date()
    fred = _fred_client()
    results, errors = [], []
    for series_id, label in VINTAGE_INDICATORS.items():
        try:
            df = fetch_vintages(fred, series_id, label)
            key = upload_to_s3(df, label, run_date)
            results.append({
                "series_id": series_id,
                "label": label,
                "rows": len(df),
                "s3_key": key,
                "run_date": run_date.isoformat(),
            })
        except Exception as exc:
            logger.error("Failed to process %s: %s", series_id, exc)
            errors.append({"series_id": series_id, "error": str(exc)})

    logger.info("Run complete -- %d succeeded, %d failed", len(results), len(errors))
    print(json.dumps({"successes": results, "failures": errors}, indent=2))
    return results


if __name__ == "__main__":
    run_all()
