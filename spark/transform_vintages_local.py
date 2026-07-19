"""
Transforms raw ALFRED vintage CSVs into one long table: one row per
(series, observation date, release date, value). Deduped so re-running the
daily refresh never double-counts a vintage.

Output: s3://<bucket>/processed/fred_vintages/part-0.parquet
The dbt layer adds first-release / latest-value window columns on top.
"""

import io
import os

import boto3
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

BUCKET = os.environ["AWS_BUCKET_NAME"]
REGION = os.environ.get("AWS_REGION", "us-east-1")
RAW_PREFIX = "raw/vintages"
PROCESSED_KEY = "processed/fred_vintages/part-0.parquet"

LABELS = ["gdp", "nonfarm_payrolls", "unemployment_rate", "housing_starts"]


def s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        region_name=REGION,
    )


def read_raw_label(s3, label: str) -> pd.DataFrame:
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
    df["release_date"] = pd.to_datetime(df["release_date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = (
        df.dropna(subset=["date", "release_date", "value"])
        .drop_duplicates(subset=["date", "release_date"], keep="last")
        .sort_values(["date", "release_date"])
        .reset_index(drop=True)
    )
    df["label"] = label
    return df[["label", "series_id", "date", "release_date", "value"]]


def run() -> pd.DataFrame:
    s3 = s3_client()
    frames = [read_raw_label(s3, label) for label in LABELS]
    long = pd.concat(frames, ignore_index=True)

    buf = io.BytesIO()
    long.to_parquet(buf, engine="pyarrow", compression="snappy", index=False)
    buf.seek(0)
    s3.put_object(Bucket=BUCKET, Key=PROCESSED_KEY, Body=buf.getvalue())
    print(f"Wrote {len(long)} rows to s3://{BUCKET}/{PROCESSED_KEY}")
    return long


if __name__ == "__main__":
    result = run()
    print(result.groupby("label").size().to_string())
