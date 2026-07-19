"""
Transforms the raw state-level CSVs into one long table:
one row per (date, state), with the three indicators outer-joined and
year-over-year changes computed per state on each indicator's own
observation frequency (monthly unemployment, quarterly house prices,
annual income) before the join, so mixed frequencies never contaminate
each other's changes.

Output: s3://<bucket>/processed/state_indicators/part-0.parquet
"""

import io
import os

import boto3
import pandas as pd
from dotenv import load_dotenv

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "ingestion"))
from fetch_fred_states import STATES  # noqa: E402  (single source of truth for names)

load_dotenv()

BUCKET = os.environ["AWS_BUCKET_NAME"]
REGION = os.environ.get("AWS_REGION", "us-east-1")
RAW_PREFIX = "raw/states"
PROCESSED_KEY = "processed/state_indicators/part-0.parquet"

INDICATORS = ["unemployment_rate", "house_price_index", "per_capita_income"]

# periods that make up one year at each indicator's native frequency
YOY_PERIODS = {
    "unemployment_rate": 12,  # monthly
    "house_price_index": 4,   # quarterly
    "per_capita_income": 1,   # annual
}


def s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        region_name=REGION,
    )


def read_raw_indicator(s3, label: str) -> pd.DataFrame:
    prefix = f"{RAW_PREFIX}/{label}/"
    paginator = s3.get_paginator("list_objects_v2")
    keys = [
        obj["Key"]
        for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix)
        for obj in page.get("Contents", [])
        if obj["Key"].endswith(".csv")
    ]
    if not keys:
        raise FileNotFoundError(f"No raw CSVs found under s3://{BUCKET}/{prefix}")

    frames = []
    for key in keys:
        obj = s3.get_object(Bucket=BUCKET, Key=key)
        frames.append(pd.read_csv(io.BytesIO(obj["Body"].read())))

    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = (
        df.dropna(subset=["date", "value", "state"])
        .drop_duplicates(subset=["date", "state"], keep="last")
        .sort_values(["state", "date"])
        .rename(columns={"value": label})[["date", "state", label]]
        .reset_index(drop=True)
    )
    return df


def add_yoy(df: pd.DataFrame, label: str) -> pd.DataFrame:
    df = df.copy()
    periods = YOY_PERIODS[label]
    grouped = df.groupby("state")[label]
    if label == "unemployment_rate":
        # a rate: year-over-year change in percentage points
        df[f"{label}_yoy"] = grouped.diff(periods)
    else:
        # a level: year-over-year percent change
        df[f"{label}_yoy_pct"] = grouped.pct_change(periods) * 100
    return df


def run() -> pd.DataFrame:
    s3 = s3_client()
    wide = None

    for label in INDICATORS:
        print(f"Processing {label}...")
        raw = read_raw_indicator(s3, label)
        featured = add_yoy(raw, label)
        wide = (
            featured if wide is None
            else wide.merge(featured, on=["date", "state"], how="outer")
        )

    wide = wide.sort_values(["state", "date"]).reset_index(drop=True)
    wide["state_name"] = wide["state"].map(STATES)

    buf = io.BytesIO()
    wide.to_parquet(buf, engine="pyarrow", compression="snappy", index=False)
    buf.seek(0)
    s3.put_object(Bucket=BUCKET, Key=PROCESSED_KEY, Body=buf.getvalue())
    print(f"Wrote {len(wide)} rows to s3://{BUCKET}/{PROCESSED_KEY}")
    return wide


if __name__ == "__main__":
    result = run()
    print(result.tail(6).to_string())
