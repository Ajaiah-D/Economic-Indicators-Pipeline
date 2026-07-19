"""
State-level FRED ingestion: unemployment rate, FHFA house price index, and
per-capita personal income for all 50 states plus DC (~150 series).

Unlike fetch_fred.py (one CSV per national series), this batches each
indicator into a single long CSV (date, state, value) per run -- 153 tiny
S3 objects a day would just be clutter, and the downstream transform wants
the long shape anyway.

FRED rate-limits at 120 requests/minute, so requests are spaced out; a full
run takes about 90 seconds.
"""

import io
import json
import logging
import os
import time
from datetime import date, datetime

import boto3
import pandas as pd
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from fredapi import Fred

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
    "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}

# label -> FRED series-id pattern ({code} is the two-letter postal code).
# UR is monthly, STHPI (FHFA all-transactions index) quarterly, PCPI annual.
STATE_INDICATORS = {
    "unemployment_rate": "{code}UR",
    "house_price_index": "{code}STHPI",
    "per_capita_income": "{code}PCPI",
}

# 120 req/min allowed; leave headroom so a retry never trips the limit
REQUEST_SPACING_SECONDS = 0.55


def _fred_client() -> Fred:
    return Fred(api_key=os.environ["FRED_API_KEY"])


def _s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )


def fetch_indicator(fred: Fred, label: str, pattern: str) -> tuple[pd.DataFrame, list[dict]]:
    """One long DataFrame (date, state, value) covering every state."""
    frames, errors = [], []
    for code in STATES:
        series_id = pattern.format(code=code)
        try:
            data = fred.get_series(series_id)
            df = (
                data.rename_axis("date")
                .reset_index()
                .rename(columns={0: "value"})
                .assign(state=code, series_id=series_id)
            )
            frames.append(df)
        except Exception as exc:
            logger.error("Failed %s (%s): %s", series_id, label, exc)
            errors.append({"series_id": series_id, "error": str(exc)})
        time.sleep(REQUEST_SPACING_SECONDS)

    if not frames:
        return pd.DataFrame(), errors
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.date.astype(str)
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    logger.info("Fetched %s: %d rows across %d states", label, len(out), len(frames))
    return out, errors


def upload_to_s3(df: pd.DataFrame, label: str, run_date: date) -> str:
    key = f"raw/states/{label}/{run_date.isoformat()}/{label}.csv"
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
    for label, pattern in STATE_INDICATORS.items():
        df, errs = fetch_indicator(fred, label, pattern)
        errors.extend(errs)
        if df.empty:
            continue
        key = upload_to_s3(df, label, run_date)
        results.append({
            "label": label,
            "rows": len(df),
            "states": df["state"].nunique(),
            "s3_key": key,
            "run_date": run_date.isoformat(),
        })

    logger.info("Run complete -- %d indicators uploaded, %d series failed", len(results), len(errors))
    print(json.dumps({"successes": results, "failures": errors}, indent=2))
    return results


if __name__ == "__main__":
    run_all()
