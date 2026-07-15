"""
Exports the dbt marts.economic_dashboard table to a committed Parquet
snapshot at data/economic_dashboard.parquet, and writes a small metadata
file at data/last_updated.json.

This is what the deployed dashboard reads when there's no local dbt build
available (e.g. a Streamlit Community Cloud deploy, which only has whatever
is checked into git). Run this after `dbt run` -- it does not run dbt itself.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).parent.parent
DUCKDB_PATH = REPO_ROOT / "dbt" / "target" / "fred_pipeline.duckdb"
SNAPSHOT_PARQUET = REPO_ROOT / "data" / "economic_dashboard.parquet"
LAST_UPDATED_JSON = REPO_ROOT / "data" / "last_updated.json"


def run() -> None:
    SNAPSHOT_PARQUET.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    con.execute(
        f"COPY main_marts.economic_dashboard TO '{SNAPSHOT_PARQUET.as_posix()}' (FORMAT PARQUET)"
    )
    row_count, min_date, max_date = con.execute(
        "SELECT count(*), min(date), max(date) FROM main_marts.economic_dashboard"
    ).fetchone()
    con.close()

    metadata = {
        "last_updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "row_count": row_count,
        "date_range": {
            "start": str(min_date),
            "end": str(max_date),
        },
    }
    LAST_UPDATED_JSON.write_text(json.dumps(metadata, indent=2) + "\n")

    print(f"Wrote {row_count} rows to {SNAPSHOT_PARQUET}")
    print(f"Wrote metadata to {LAST_UPDATED_JSON}: {metadata}")


if __name__ == "__main__":
    run()
