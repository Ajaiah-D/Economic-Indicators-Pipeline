"""
Local pandas implementation of the indicator transform.

Same MoM % change, 3-month rolling average, and full outer join as the
PySpark job in transform_indicators.py, but without a Spark cluster. The
whole dataset is a few hundred rows per series, so pandas is plenty here;
the Spark version is kept for running the same logic at scale on Databricks.
"""

import io
import os

import boto3
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

BUCKET = os.environ["AWS_BUCKET_NAME"]
REGION = os.environ.get("AWS_REGION", "us-east-1")
RAW_PREFIX = "raw"
PROCESSED_KEY = "processed/economic_indicators/part-0.parquet"

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

ROLLING_WINDOW = 3


def s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        region_name=REGION,
    )


def read_raw_series(s3, series_id: str, label: str) -> pd.DataFrame:
    prefix = f"{RAW_PREFIX}/{label}/"
    paginator = s3.get_paginator("list_objects_v2")
    keys = [
        obj["Key"]
        for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix)
        for obj in page.get("Contents", [])
        if obj["Key"].endswith(f"{series_id}.csv")
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
        df.dropna(subset=["date", "value"])
        .drop_duplicates(subset=["date"], keep="last")
        .sort_values("date")
        .rename(columns={"value": label})[["date", label]]
        .reset_index(drop=True)
    )
    return df


def add_features(df: pd.DataFrame, label: str) -> pd.DataFrame:
    df = df.copy()
    df[f"{label}_mom_pct"] = df[label].pct_change() * 100
    df[f"{label}_3m_avg"] = df[label].rolling(ROLLING_WINDOW).mean()
    return df


def run() -> pd.DataFrame:
    s3 = s3_client()
    wide = None

    for series_id, label in INDICATORS.items():
        print(f"Processing {series_id}...")
        raw = read_raw_series(s3, series_id, label)
        featured = add_features(raw, label)
        wide = featured if wide is None else wide.merge(featured, on="date", how="outer")

    wide = wide.sort_values("date").reset_index(drop=True)

    # 10-year minus 3-month Treasury spread -- a negative (inverted) spread
    # is the single most established recession precursor in macro
    wide["yield_spread"] = wide["treasury_10y"] - wide["treasury_3m"]

    buf = io.BytesIO()
    wide.to_parquet(buf, engine="pyarrow", compression="snappy", index=False)
    buf.seek(0)
    s3.put_object(Bucket=BUCKET, Key=PROCESSED_KEY, Body=buf.getvalue())
    print(f"Wrote {len(wide)} rows to s3://{BUCKET}/{PROCESSED_KEY}")
    return wide


if __name__ == "__main__":
    result = run()
    print(result.tail(10).to_string())
