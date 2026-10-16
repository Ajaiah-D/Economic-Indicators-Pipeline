import pandas as pd

import app


def _national_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(["2026-06-01", "2026-07-01", "2026-08-01"]),
        "cpi": [320.0, 321.0, 322.0],
        "cpi_mom_pct": [None, 0.3125, 0.3115],
        "unemployment_rate": [4.1, 4.2, None],
        "unemployment_rate_mom_pct": [None, 2.439, None],
        "yield_spread": [0.50, 0.40, 0.65],
        "gdp": [None, None, None],
        "gdp_mom_pct": [None, None, None],
    })


def test_cpi_tile_is_neutral_and_has_a_sparkline():
    tile = app.kpi_tile(_national_frame(), "cpi")
    assert tile.label == "CPI"
    assert tile.value == "322.0"
    assert tile.change == "+0.31% MoM"
    assert tile.delta == 0.31
    assert tile.tone == "neutral"
    assert tile.caption == "as of Aug 2026"
    assert 'class="civic-spark civic-spark-0"' in tile.spark


def test_tile_reads_the_series_own_latest_row():
    tile = app.kpi_tile(_national_frame(), "unemployment_rate")
    assert tile.value == "4.2%"
    assert tile.change == "+2.44% MoM"
    assert tile.tone == "bad"
    assert tile.caption == "as of Jul 2026"


def test_yield_spread_change_is_in_points_and_a_rise_is_good():
    tile = app.kpi_tile(_national_frame(), "yield_spread")
    assert tile.value == "+0.65pt"
    assert tile.change == "+0.25pt MoM"
    assert tile.tone == "good"


def test_series_without_data_shows_na():
    tile = app.kpi_tile(_national_frame(), "gdp")
    assert tile.value == "N/A"
    assert tile.change is None
    assert tile.caption == ""
    assert tile.spark == ""


def test_status_for_score_keeps_three_states():
    assert app.status_for_score(5, True) == ("watch", "Recession watch")
    assert app.status_for_score(3, False) == ("elevated", "Elevated risk")
    assert app.status_for_score(1, False) == ("clear", "No recession watch")


def test_every_series_has_a_palette_slot():
    assert sorted(m["slot"] for m in app.INDICATOR_META.values()) == list(range(8))
    assert all("color" not in m for m in app.INDICATOR_META.values())
