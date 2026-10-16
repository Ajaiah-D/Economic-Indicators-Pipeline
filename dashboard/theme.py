"""
Design tokens, theme selection, chart palettes and chart helpers for every
dashboard page (the "Civic" visual system).

LIGHT and DARK mirror the [theme.light] / [theme.dark] tables in
.streamlit/config.toml; tests/test_theme.py fails if they drift. tokens()
picks one set per script run from st.context.theme.type. The page CSS in
ui.py carries BOTH sets through CSS light-dark(), so the app's own HTML
follows a theme switch at once; Plotly figures use tokens() and follow it on
the next rerun (Streamlit only reports the theme with a rerun).
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

FONT = "Arial, Helvetica, sans-serif"
FOCUS = "#ffdd00"  # GOV.UK focus yellow, the same in both modes

# The spec's tokens, verbatim. CAUTION is the amber middle step the signal
# banner uses for "Elevated risk", always next to its text label.
LIGHT = {
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
DARK = {
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


def _theme_type() -> str | None:
    """"light" or "dark" as the browser last reported it. None (or "") before
    it has reported, outside a script run, and under AppTest."""
    return st.context.theme.type


def mode() -> str:
    return "dark" if _theme_type() == "dark" else "light"


def tokens(theme_mode: str | None = None) -> dict[str, str]:
    return DARK if (theme_mode or mode()) == "dark" else LIGHT


# --------------------------------------------------------------------------- #
# Change arrows. The arrow always shows the actual direction; the colour says
# whether that move is good for the economy. The text value is always shown
# next to it, so colour is never the only cue. Keys are the series in
# app.INDICATOR_META (a test keeps them identical); the directions agree with
# briefing.py's warn/good tones.
# --------------------------------------------------------------------------- #
GOOD_DIRECTION: dict[str, str] = {
    "cpi": "none",
    "unemployment_rate": "down",
    "u6_rate": "down",
    "gdp": "up",
    "fed_funds_rate": "none",
    "housing_starts": "up",
    "consumer_sentiment": "up",
    "yield_spread": "up",
}

ARROW_UP = "▲"
ARROW_DOWN = "▼"
ARROW_FLAT = "▬"


def _is_zero_or_missing(delta: float | None) -> bool:
    # pd.isna covers None, NaN and pandas NA, which float() would raise on
    return delta is None or bool(pd.isna(delta)) or float(delta) == 0.0


def arrow(delta: float | None) -> str:
    if _is_zero_or_missing(delta):
        return ARROW_FLAT
    return ARROW_UP if float(delta) > 0 else ARROW_DOWN


def change_tone(good_direction: str, delta: float | None) -> str:
    """"good" if the move matches the good direction, "bad" if it goes
    against it, "neutral" for no change or an indicator with no good side."""
    if good_direction not in ("up", "down", "none"):
        raise ValueError(f"unknown good direction {good_direction!r}")
    if good_direction == "none" or _is_zero_or_missing(delta):
        return "neutral"
    rising = float(delta) > 0
    return "good" if rising == (good_direction == "up") else "bad"


# --------------------------------------------------------------------------- #
# Chart palettes, one list per mode. Validated with the dataviz skill's
# validate_palette.js against each mode's PAGE and SURFACE (civic-ui plan,
# Task 3); re-run it after changing any hex.
#   light vs #ffffff and #f3f3f3: all PASS; worst adjacent CVD dE 18.1
#     (#009b9f/#7a6100, deutan), normal-vision dE 20.8, all >= 3:1
#   dark vs #151b22 and #1e2630: all PASS; worst adjacent CVD dE 16.7
#     (#5e8fed/#b3487e, deutan), normal-vision dE 20.9, all >= 3:1
#   every sequential ramp and diverging arm: --ordinal ALL CHECKS PASS
# Series never reuse GOOD/BAD (OKLab dE >= 12 from both, in either mode);
# no slot is a pure blue. Slot order = app.INDICATOR_META order.
# --------------------------------------------------------------------------- #
SERIES = {
    # 0 violet, 1 ochre, 2 plum, 3 olive, 4 magenta, 5 slate blue, 6 dark gold, 7 teal
    "light": ["#654db6", "#b27a00", "#8e3b94", "#7f9200", "#a2316d", "#4e82e5", "#7a6100", "#009b9f"],
    "dark": ["#7561c5", "#c18500", "#9f51a4", "#8b9e0f", "#b3487e", "#5e8fed", "#8d7200", "#00a8ad"],
}

# Sequential ramps (choropleth magnitude), low -> high. In dark mode the
# anchor flips: low values sit near the dark surface, high values are light.
SEQ_TEAL = {
    "light": ["#26c0cf", "#009fac", "#007e89", "#005e66", "#004148"],
    "dark": ["#00646d", "#00818c", "#009fac", "#3abbc8", "#5ed9e6"],
}
SEQ_PURPLE = {
    "light": ["#bf93f1", "#a074d0", "#8256af", "#65398f", "#491a70"],
    "dark": ["#694191", "#835bae", "#9f76cb", "#bb92e9", "#d5b2fe"],
}
# Diverging (polarity): ochre arm for negative, neutral grey midpoint, slate
# arm for positive; both arms recede toward the midpoint.
DIVERGING = {
    "light": ["#875800", "#b37903", "#da9e3f", "#eef0f2", "#73b0ee", "#4984bf", "#1d5b92"],
    "dark": ["#d79f4c", "#b07a20", "#875800", "#2a333d", "#32669a", "#558ac0", "#79b0e8"],
}

PLOTLY_CONFIG = {"displayModeBar": False}


def series_palette(theme_mode: str | None = None) -> list[str]:
    return list(SERIES[theme_mode or mode()])


def series_color(slot: int, theme_mode: str | None = None) -> str:
    return series_palette(theme_mode)[slot]


def colorscale(steps: list[str]) -> list[list]:
    """Evenly spaced Plotly colorscale from a list of hex steps."""
    last = len(steps) - 1
    return [[round(i / last, 4), colour] for i, colour in enumerate(steps)]


def rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def plotly_layout(fig: go.Figure, height: int, *, hovermode: str = "x unified",
                  theme_mode: str | None = None) -> go.Figure:
    """The one chart look: transparent background, Arial, hairline y grid in
    BORDER, no x grid, unified hover. Callers pass PLOTLY_CONFIG to
    st.plotly_chart to hide the modebar."""
    t = tokens(theme_mode)
    fig.update_layout(
        height=height,
        font=dict(family=FONT, color=t["INK_2"], size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(color=t["INK_2"]), bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=0, r=8, t=34, b=0),
        hovermode=hovermode,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(bgcolor=t["SURFACE"], bordercolor=t["BORDER"],
                        font=dict(family=FONT, color=t["INK"])),
    )
    fig.update_xaxes(showgrid=False, showline=True, linecolor=t["BORDER"], zeroline=False,
                     tickfont=dict(color=t["INK_2"]))
    fig.update_yaxes(showgrid=True, gridcolor=t["BORDER"], gridwidth=1, zeroline=False,
                     showline=False, tickfont=dict(color=t["INK_2"]))
    return fig
