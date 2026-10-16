import tomllib
from pathlib import Path

import pytest

import theme

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / ".streamlit" / "config.toml"

# The spec's token table, verbatim, plus CAUTION (the banner's amber middle step).
SPEC_LIGHT = {
    "PAGE": "#ffffff",
    "SURFACE": "#f3f3f3",
    "RIBBON": "#2e3f52",
    "HEADING": "#2e3f52",
    "INK": "#0b0c0c",
    "INK_2": "#505a5f",
    "BORDER": "#cdd3d9",
    "ACCENT": "#2b5f8a",
    "TILE_RULE": "#5b7a96",
    "GOOD": "#00703c",
    "BAD": "#c2361f",
    "NEUTRAL": "#505a5f",
    "CAUTION": "#8a5a00",
}
SPEC_DARK = {
    "PAGE": "#151b22",
    "SURFACE": "#1e2630",
    "RIBBON": "#0f141a",
    "HEADING": "#eef1f4",
    "INK": "#eef1f4",
    "INK_2": "#a8b3bf",
    "BORDER": "#3a4652",
    "ACCENT": "#9fc1e0",
    "TILE_RULE": "#8fa9c2",
    "GOOD": "#5cc98f",
    "BAD": "#ff8a78",
    "NEUTRAL": "#a8b3bf",
    "CAUTION": "#e0a43a",
}

# config.toml option -> theme token, for [theme.<mode>] and [theme.<mode>.sidebar]
MAIN_ROLES = {
    "primaryColor": "ACCENT",
    "backgroundColor": "PAGE",
    "secondaryBackgroundColor": "SURFACE",
    "textColor": "INK",
    "linkColor": "ACCENT",
    "borderColor": "BORDER",
}
SIDEBAR_ROLES = {
    "backgroundColor": "SURFACE",
    "secondaryBackgroundColor": "PAGE",
    "textColor": "INK",
    "borderColor": "BORDER",
}


def _config() -> dict:
    with CONFIG.open("rb") as fh:
        return tomllib.load(fh)


def test_token_sets_have_identical_keys():
    assert list(theme.LIGHT) == list(theme.DARK)


def test_tokens_match_the_spec():
    assert theme.LIGHT == SPEC_LIGHT
    assert theme.DARK == SPEC_DARK
    assert theme.FONT == "Arial, Helvetica, sans-serif"
    assert theme.FOCUS == "#ffdd00"


@pytest.mark.parametrize(
    "reported, expected",
    [(None, "light"), ("", "light"), ("light", "light"), ("dark", "dark"), ("sepia", "light")],
)
def test_mode_follows_the_browser_and_falls_back_to_light(monkeypatch, reported, expected):
    monkeypatch.setattr(theme, "_theme_type", lambda: reported)
    assert theme.mode() == expected
    assert theme.tokens() is (theme.DARK if expected == "dark" else theme.LIGHT)


def test_tokens_accepts_an_explicit_mode():
    assert theme.tokens("dark") is theme.DARK
    assert theme.tokens("light") is theme.LIGHT


def test_mode_is_light_outside_a_script_run():
    # plain import, no Streamlit script-run context: st.context.theme.type is None
    assert theme.mode() == "light"


@pytest.mark.parametrize("name", ["light", "dark"])
def test_config_toml_matches_tokens(name):
    tokens = theme.LIGHT if name == "light" else theme.DARK
    table = dict(_config()["theme"][name])
    sidebar = table.pop("sidebar")
    assert table == {opt: tokens[role] for opt, role in MAIN_ROLES.items()}
    assert sidebar == {opt: tokens[role] for opt, role in SIDEBAR_ROLES.items()}


def test_config_shared_theme_options():
    shared = {k: v for k, v in _config()["theme"].items() if not isinstance(v, dict)}
    assert shared == {
        "font": theme.FONT,
        "headingFont": theme.FONT,
        "baseRadius": "0px",
        "buttonRadius": "0px",
        "showSidebarBorder": True,
    }


def test_config_has_only_light_and_dark_tables():
    # the old single-mode [theme.sidebar] table and `base` must be gone
    tables = {k for k, v in _config()["theme"].items() if isinstance(v, dict)}
    assert tables == {"light", "dark"}


import ast
import math

import briefing


def _indicator_meta_keys() -> set[str]:
    """The app's real series list: the keys of INDICATOR_META in app.py."""
    tree = ast.parse((ROOT / "dashboard" / "app.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "INDICATOR_META" for t in node.targets):
            return {key.value for key in node.value.keys}
    raise AssertionError("no top-level INDICATOR_META in dashboard/app.py")


def test_every_series_has_a_good_direction():
    assert set(theme.GOOD_DIRECTION) == _indicator_meta_keys()
    # the briefing names the same eight series
    assert set(theme.GOOD_DIRECTION) == set(briefing.QUIET_LABELS)


def test_good_directions_are_the_agreed_ones():
    assert theme.GOOD_DIRECTION == {
        "cpi": "none",
        "unemployment_rate": "down",
        "u6_rate": "down",
        "gdp": "up",
        "fed_funds_rate": "none",
        "housing_starts": "up",
        "consumer_sentiment": "up",
        "yield_spread": "up",
    }


@pytest.mark.parametrize(
    "direction, delta, expected",
    [
        ("up", 1.5, "good"),
        ("up", -1.5, "bad"),
        ("up", 0.0, "neutral"),
        ("down", 1.5, "bad"),
        ("down", -1.5, "good"),
        ("down", 0.0, "neutral"),
        ("none", 1.5, "neutral"),
        ("none", -1.5, "neutral"),
        ("none", 0.0, "neutral"),
        ("up", None, "neutral"),
        ("down", math.nan, "neutral"),
    ],
)
def test_change_tone_covers_every_direction_and_move(direction, delta, expected):
    assert theme.change_tone(direction, delta) == expected


def test_change_tone_rejects_an_unknown_direction():
    with pytest.raises(ValueError):
        theme.change_tone("sideways", 1.0)


@pytest.mark.parametrize(
    "delta, expected",
    [(0.25, "▲"), (-0.25, "▼"), (0.0, "▬"), (None, "▬"), (math.nan, "▬")],
)
def test_arrow_always_shows_the_actual_direction(delta, expected):
    assert theme.arrow(delta) == expected


import plotly.graph_objects as go


def _oklab(hex_color: str) -> tuple[float, float, float]:
    def lin(channel: int) -> float:
        c = channel / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(int(hex_color[i:i + 2], 16)) for i in (1, 3, 5))
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def _delta_e(a: str, b: str) -> float:
    return 100 * math.dist(_oklab(a), _oklab(b))


@pytest.mark.parametrize("name", ["light", "dark"])
def test_series_palette_has_eight_slots_clear_of_status_colours(name):
    tokens = theme.LIGHT if name == "light" else theme.DARK
    palette = theme.SERIES[name]
    assert len(palette) == 8 == len(set(palette))
    for colour in palette:
        assert colour not in (tokens["GOOD"], tokens["BAD"])
        assert _delta_e(colour, tokens["GOOD"]) >= 10, colour
        assert _delta_e(colour, tokens["BAD"]) >= 10, colour


def test_series_palette_follows_mode(monkeypatch):
    monkeypatch.setattr(theme, "_theme_type", lambda: "dark")
    assert theme.series_palette() == theme.SERIES["dark"]
    assert theme.series_color(3) == theme.SERIES["dark"][3]
    assert theme.series_palette("light") == theme.SERIES["light"]


@pytest.mark.parametrize("ramp, steps", [(theme.SEQ_TEAL, 5), (theme.SEQ_PURPLE, 5), (theme.DIVERGING, 7)])
def test_ramps_exist_for_both_modes(ramp, steps):
    assert set(ramp) == {"light", "dark"}
    assert len(ramp["light"]) == len(ramp["dark"]) == steps


def test_colorscale_spreads_steps_from_zero_to_one():
    scale = theme.colorscale(["#000000", "#777777", "#ffffff"])
    assert scale == [[0.0, "#000000"], [0.5, "#777777"], [1.0, "#ffffff"]]


@pytest.mark.parametrize("name", ["light", "dark"])
def test_plotly_layout_is_theme_aware_and_square(name):
    tokens = theme.LIGHT if name == "light" else theme.DARK
    fig = theme.plotly_layout(go.Figure(go.Scatter(x=[1, 2], y=[3, 4])), height=300, theme_mode=name)
    layout = fig.layout
    assert layout.height == 300
    assert layout.paper_bgcolor == layout.plot_bgcolor == "rgba(0,0,0,0)"
    assert layout.font.family == theme.FONT
    assert layout.font.color == tokens["INK_2"]
    assert layout.hovermode == "x unified"
    assert layout.xaxis.showgrid is False
    assert layout.yaxis.showgrid is True
    assert layout.yaxis.gridcolor == tokens["BORDER"]
    assert layout.hoverlabel.bgcolor == tokens["SURFACE"]


def test_plotly_layout_hovermode_can_be_overridden():
    fig = theme.plotly_layout(go.Figure(), height=200, hovermode="closest", theme_mode="light")
    assert fig.layout.hovermode == "closest"


def test_plotly_config_hides_the_modebar():
    assert theme.PLOTLY_CONFIG == {"displayModeBar": False}


def test_missing_values_include_pandas_na():
    import pandas as pd

    assert theme.change_tone("up", pd.NA) == "neutral"
    assert theme.change_tone("down", pd.NA) == "neutral"
    assert theme.arrow(pd.NA) == "▬"


LEGACY_NAMES = (
    "INK_PRIMARY", "INK_SECONDARY", "INK_MUTED", "GRIDLINE", "SURFACE", "PAGE", "SIDEBAR",
    "STATUS", "SEQ_BLUE", "SEQ_GREEN", "DIV_AMBER_BLUE", "base_layout", "sparkline",
)


@pytest.mark.parametrize("name", LEGACY_NAMES)
def test_legacy_theme_names_are_gone(name):
    assert not hasattr(theme, name)
