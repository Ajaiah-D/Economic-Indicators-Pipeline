"""
Exports the dbt mart tables to committed Parquet snapshots under data/
(economic_dashboard.parquet, state_dashboard.parquet), and writes a small
metadata file at data/last_updated.json.

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
DATA_DIR = REPO_ROOT / "data"
LAST_UPDATED_JSON = DATA_DIR / "last_updated.json"

# mart table -> snapshot filename. A mart missing from the duckdb file is
# skipped with a warning rather than failing the whole export, so the
# national snapshot still refreshes even if a state/vintage build was skipped.
MARTS = {
    "economic_dashboard": "economic_dashboard.parquet",
    "state_dashboard": "state_dashboard.parquet",
    "vintage_dashboard": "vintage_dashboard.parquet",
}


def run() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    metadata = {
        "last_updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tables": {},
    }
    for table, filename in MARTS.items():
        target = DATA_DIR / filename
        try:
            con.execute(
                f"COPY main_marts.{table} TO '{target.as_posix()}' (FORMAT PARQUET)"
            )
            row_count, min_date, max_date = con.execute(
                f"SELECT count(*), min(date), max(date) FROM main_marts.{table}"
            ).fetchone()
        except duckdb.CatalogException as exc:
            print(f"WARNING: skipping {table} -- {exc}")
            continue
        metadata["tables"][table] = {
            "row_count": row_count,
            "date_range": {"start": str(min_date), "end": str(max_date)},
        }
        print(f"Wrote {row_count} rows to {target}")
    con.close()

    # kept for anything still reading the old top-level shape
    national = metadata["tables"].get("economic_dashboard")
    if national:
        metadata["row_count"] = national["row_count"]
        metadata["date_range"] = national["date_range"]

    LAST_UPDATED_JSON.write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Wrote metadata to {LAST_UPDATED_JSON}")


if __name__ == "__main__":
    run()
