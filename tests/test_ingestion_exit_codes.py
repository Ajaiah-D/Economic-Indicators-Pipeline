import pandas as pd

import fetch_fred
import fetch_fred_states
import fetch_fred_vintages


def test_national_exits_1_when_one_series_fails(monkeypatch):
    def fake(series_id, label, run_date=None):
        if series_id == "GDP":
            raise RuntimeError("FRED is down")
        return {"series_id": series_id, "label": label, "rows": 1, "s3_key": "k", "run_date": "2026-01-01"}

    monkeypatch.setattr(fetch_fred, "fetch_and_upload", fake)
    successes, failures = fetch_fred.run_all()
    assert len(successes) == len(fetch_fred.INDICATORS) - 1
    assert [f["series_id"] for f in failures] == ["GDP"]
    assert fetch_fred.main() == 1


def test_national_exits_0_when_all_succeed(monkeypatch):
    monkeypatch.setattr(
        fetch_fred, "fetch_and_upload",
        lambda s, l, run_date=None: {"series_id": s, "label": l, "rows": 1, "s3_key": "k", "run_date": "2026-01-01"},
    )
    assert fetch_fred.main() == 0


def test_states_exits_1_when_one_state_series_fails(monkeypatch):
    frame = pd.DataFrame({"date": ["2026-01-01"], "value": [4.0], "state": ["CA"], "series_id": ["CAUR"]})
    monkeypatch.setattr(fetch_fred_states, "_fred_client", lambda: object())
    monkeypatch.setattr(
        fetch_fred_states, "fetch_indicator",
        lambda fred, label, pattern: (frame, [{"series_id": "TXUR", "error": "boom"}] if label == "unemployment_rate" else []),
    )
    monkeypatch.setattr(fetch_fred_states, "upload_to_s3", lambda df, label, run_date: "k")
    assert fetch_fred_states.main() == 1


def test_vintages_exits_1_when_one_series_fails(monkeypatch):
    frame = pd.DataFrame({"date": ["2026-01-01"], "release_date": ["2026-02-01"], "value": [1.0],
                          "series_id": ["GDP"], "label": ["gdp"]})

    def fake_fetch(fred, series_id, label):
        if series_id == "PAYEMS":
            raise RuntimeError("timeout")
        return frame

    monkeypatch.setattr(fetch_fred_vintages, "_fred_client", lambda: object())
    monkeypatch.setattr(fetch_fred_vintages, "fetch_vintages", fake_fetch)
    monkeypatch.setattr(fetch_fred_vintages, "upload_to_s3", lambda df, label, run_date: "k")
    assert fetch_fred_vintages.main() == 1
