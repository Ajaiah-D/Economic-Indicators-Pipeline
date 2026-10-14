import duckdb
import pandas as pd

import export_dashboard_snapshot as exp


def _build_db(path, stamp: str) -> None:
    con = duckdb.connect(str(path))
    con.execute("create schema if not exists main_marts")
    con.execute(
        "create or replace table main_marts.economic_dashboard as "
        f"select date '2026-01-01' as date, 1.5 as cpi, timestamp '{stamp}' as dbt_updated_at"
    )
    con.close()


def test_export_ignores_the_build_timestamp(tmp_path, monkeypatch):
    db = tmp_path / "fred.duckdb"
    data = tmp_path / "data"
    monkeypatch.setattr(exp, "DUCKDB_PATH", db)
    monkeypatch.setattr(exp, "DATA_DIR", data)
    monkeypatch.setattr(exp, "LAST_UPDATED_JSON", data / "last_updated.json")

    _build_db(db, "2026-01-01 00:00:00")
    exp.run()
    first = (data / "economic_dashboard.parquet").read_bytes()

    _build_db(db, "2026-01-02 12:34:56")  # same data, rebuilt a day later
    exp.run()
    second = (data / "economic_dashboard.parquet").read_bytes()

    assert "dbt_updated_at" not in pd.read_parquet(data / "economic_dashboard.parquet").columns
    assert first == second
