"""
Backtests the recession-watch signal against every NBER recession since 1959
(the first year all indicators overlap), using the committed national snapshot.

Definitions, matching the README:
  near a recession  a month between `LEAD_MONTHS` before the NBER peak and the trough
  caught            recession_watch is true in at least one of those months
  lead              months from the first such watch month to the peak, so it is
                    capped at LEAD_MONTHS and goes negative when the watch only
                    switched on after the recession had started

These are in-sample figures on today's revised data, not a forecast record.

Run: python scripts/backtest_signal.py
"""

import json
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
SNAPSHOT = REPO_ROOT / "data" / "economic_dashboard.parquet"

# (peak month, trough month), NBER business-cycle dates
NBER_RECESSIONS = [
    ("1960-04-01", "1961-02-01"),
    ("1969-12-01", "1970-11-01"),
    ("1973-11-01", "1975-03-01"),
    ("1980-01-01", "1980-07-01"),
    ("1981-07-01", "1982-11-01"),
    ("1990-07-01", "1991-03-01"),
    ("2001-03-01", "2001-11-01"),
    ("2007-12-01", "2009-06-01"),
    ("2020-02-01", "2020-04-01"),
]
WINDOW_START = "1959-01-01"
LEAD_MONTHS = 6


def backtest(df, recessions=NBER_RECESSIONS, start=WINDOW_START, lead_months=LEAD_MONTHS) -> dict:
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d[d["date"] >= start].sort_values("date").set_index("date")
    watch = d["recession_watch"].astype(bool)

    near = pd.Series(False, index=d.index)
    per_recession = []
    for peak, trough in recessions:
        peak, trough = pd.Timestamp(peak), pd.Timestamp(trough)
        in_window = (d.index >= peak - pd.DateOffset(months=lead_months)) & (d.index <= trough)
        near |= in_window
        hits = watch[in_window]
        hits = hits[hits]
        lead = None
        if len(hits):
            first = hits.index[0]
            lead = (peak.year - first.year) * 12 + (peak.month - first.month)
        per_recession.append({
            "peak": peak.strftime("%Y-%m"),
            "caught": lead is not None,
            "lead_months": lead,
        })

    flagged = int(watch.sum())
    return {
        "months": len(d),
        "flagged_months": flagged,
        "flagged_pct": round(100 * flagged / len(d), 1),
        "precision_pct": round(100 * int((watch & near).sum()) / flagged, 1) if flagged else None,
        "recall": sum(r["caught"] for r in per_recession),
        "recessions": len(per_recession),
        "per_recession": per_recession,
    }


if __name__ == "__main__":
    print(json.dumps(backtest(pd.read_parquet(SNAPSHOT)), indent=2))
