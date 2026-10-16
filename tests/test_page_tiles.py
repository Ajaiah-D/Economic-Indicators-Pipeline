import pandas as pd

import app
import revisions_view
import states_view


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


def _state_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(["2025-01-01", "2026-07-01"]),
        "unemployment_rate": [4.0, 4.5],
        "unemployment_rate_yoy": [None, 0.3],
        "unemployment_rank": [None, 20],
        "house_price_index_yoy_pct": [5.2, None],
        "hpi_growth_rank": [3, None],
        "per_capita_income": [70123.0, None],
        "per_capita_income_yoy_pct": [4.1, None],
        "income_rank": [1, None],
    })


def test_state_tiles():
    unemployment, hpi, income = states_view.kpi_tiles(_state_frame(), 51)
    assert (unemployment.label, unemployment.value) == ("Unemployment rate", "4.5%")
    assert unemployment.change == "+0.3pp YoY" and unemployment.tone == "bad"
    assert unemployment.caption == "as of Jul 2026 · 20th lowest of 51"
    assert (hpi.label, hpi.value, hpi.change) == ("House-price growth", "+5.2% YoY", None)
    assert hpi.caption == "as of Q1 2025 · 3rd fastest-growing of 51"
    assert (income.label, income.value) == ("Per-capita income", "$70,123")
    assert income.change == "+4.1% YoY" and income.tone == "good"
    assert income.caption == "as of 2025 · highest of 51"


def test_state_tiles_show_na_without_data():
    empty = _state_frame().iloc[0:0]
    labels = [(t.label, t.value) for t in states_view.kpi_tiles(empty, 51)]
    assert labels == [("Unemployment rate", "N/A"), ("House-price growth", "N/A"), ("Per-capita income", "N/A")]


def test_revision_tiles():
    rev = pd.DataFrame({
        "date": pd.to_datetime(["2008-07-01", "2008-10-01", "2009-01-01"]),
        "revision_pp": [0.5, -1.2, 0.1],
        "sign_flip": [False, True, False],
    })
    flips, largest, average = revisions_view.revision_tiles(rev)
    assert (flips.label, flips.value) == ("Quarters whose growth later flipped sign", "1 of 3")
    assert flips.caption == "reported growth when the economy was shrinking, or vice versa"
    assert (largest.value, largest.change, largest.show_arrow) == ("-1.2pp", "Q4 2008", False)
    assert largest.caption == "difference between the first print and today's estimate"
    assert average.value == "0.60pp"
    assert average.caption == "mean absolute change in quarterly growth since first print"


def test_state_map_ramps_cover_both_modes():
    for spec in states_view.METRICS.values():
        assert set(spec["ramp"]) == {"light", "dark"}
        assert "colorscale" not in spec
