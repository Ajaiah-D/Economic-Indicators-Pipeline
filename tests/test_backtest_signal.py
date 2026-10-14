from pathlib import Path

import pandas as pd

from backtest_signal import backtest

SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "economic_dashboard.parquet"


def _frame(watch_months: list[str]) -> pd.DataFrame:
    dates = pd.date_range("1959-01-01", "1962-12-01", freq="MS")
    return pd.DataFrame({
        "date": dates,
        "recession_watch": [d.strftime("%Y-%m") in watch_months for d in dates],
    })


def test_counts_lead_precision_and_recall():
    # one recession, peak Apr 1960, trough Feb 1961
    result = backtest(_frame(["1960-01", "1962-06"]), recessions=[("1960-04-01", "1961-02-01")])
    assert result["months"] == 48
    assert result["flagged_months"] == 2
    assert result["precision_pct"] == 50.0  # Jan 1960 is near, Jun 1962 is not
    assert result["recall"] == 1
    assert result["per_recession"][0]["lead_months"] == 3


def test_recession_with_no_watch_is_a_miss():
    result = backtest(_frame(["1962-06"]), recessions=[("1960-04-01", "1961-02-01")])
    assert result["recall"] == 0
    assert result["per_recession"][0] == {"peak": "1960-04", "caught": False, "lead_months": None}
    assert result["precision_pct"] == 0.0


def test_committed_snapshot_still_catches_every_recession():
    # the README claims 9 of 9; if a data revision ever breaks that, fail loudly
    result = backtest(pd.read_parquet(SNAPSHOT))
    assert result["recessions"] == 9
    assert result["recall"] == 9
    assert result["precision_pct"] >= 50
