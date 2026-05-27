"""
Reads raw indicator CSVs from S3, computes MoM % change and 3-month rolling
averages for each series, joins them into a single wide table by date, and
writes the result back to S3 as Parquet.

Designed for Databricks Community Edition. Can also be run locally via
spark-submit if you have the S3A JARs on the classpath.
"""

import os
from functools import reduce

from dotenv import load_dotenv
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql import Window
from pyspark.sql.types import DateType, DoubleType

load_dotenv()

BUCKET = os.environ.get("AWS_BUCKET_NAME", "fred-pipeline-bucket")
AWS_KEY = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

RAW_BASE = f"s3a://{BUCKET}/raw"
PROCESSED_PATH = f"s3a://{BUCKET}/processed/economic_indicators"

INDICATORS = {
    "CPIAUCSL": "cpi",
    "UNRATE": "unemployment_rate",
    "GDP": "gdp",
    "FEDFUNDS": "fed_funds_rate",
    "HOUST": "housing_starts",
    "UMCSENT": "consumer_sentiment",
}

ROLLING_WINDOW = 3


def get_spark() -> SparkSession:
    builder = SparkSession.builder.appName("fred-economic-indicators")

    # Databricks already has S3 auth wired up via instance profiles;
    # only set explicit creds when running locally
    if "DATABRICKS_RUNTIME_VERSION" not in os.environ and AWS_KEY:
        builder = (
            builder
            .config("spark.hadoop.fs.s3a.access.key", AWS_KEY)
            .config("spark.hadoop.fs.s3a.secret.key", AWS_SECRET)
            .config("spark.hadoop.fs.s3a.endpoint", f"s3.{AWS_REGION}.amazonaws.com")
            .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        )

    return builder.getOrCreate()


def read_raw_series(spark: SparkSession, series_id: str, label: str) -> DataFrame:
    # glob across all dated partitions; dedup keeps the latest value per date
    path = f"{RAW_BASE}/{label}/*/{series_id}.csv"
    return (
        spark.read
        .option("header", "true")
        .csv(path)
        .withColumn("date", F.col("date").cast(DateType()))
        .withColumn("value", F.col("value").cast(DoubleType()))
        .select("date", F.col("value").alias(label))
        .dropna(subset=["date", label])
        .dropDuplicates(["date"])
        .orderBy("date")
    )


def add_features(df: DataFrame, label: str) -> DataFrame:
    w_lag = Window.orderBy("date")
    w_roll = Window.orderBy("date").rowsBetween(-(ROLLING_WINDOW - 1), 0)
    prev = f"{label}_prev"
    return (
        df
        .withColumn(prev, F.lag(label, 1).over(w_lag))
        .withColumn(
            f"{label}_mom_pct",
            F.round((F.col(label) - F.col(prev)) / F.col(prev) * 100, 4),
        )
        .withColumn(f"{label}_3m_avg", F.round(F.avg(label).over(w_roll), 4))
        .drop(prev)
    )


def join_indicators(dfs: list[DataFrame]) -> DataFrame:
    return reduce(lambda a, b: a.join(b, on="date", how="full"), dfs).orderBy("date")


def write_parquet(df: DataFrame, path: str) -> None:
    (
        df.write
        .mode("overwrite")
        .option("compression", "snappy")
        .parquet(path)
    )
    print(f"Wrote {df.count()} rows to {path}")


def run() -> DataFrame:
    spark = get_spark()
    featured = []

    for series_id, label in INDICATORS.items():
        print(f"Processing {series_id}...")
        raw = read_raw_series(spark, series_id, label)
        featured.append(add_features(raw, label))

    wide = join_indicators(featured)
    wide.printSchema()
    write_parquet(wide, PROCESSED_PATH)
    return wide


if __name__ == "__main__":
    run().show(20, truncate=False)
