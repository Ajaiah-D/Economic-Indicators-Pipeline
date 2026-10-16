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

import math

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
    return delta is None or math.isnan(float(delta)) or float(delta) == 0.0


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
# LEGACY tokens and helpers below: still imported by app.py, states_view.py
# and revisions_view.py. Task 6 of the civic-ui plan deletes this block.
# --------------------------------------------------------------------------- #

# Colourblind-safe ink/surface tokens. These are the single source of truth for
# every surface in the app -- .streamlit/config.toml mirrors them, and nothing
# should hardcode a background or border hex anywhere else.
#
# Surfaces deliberately avoid pure white: the page sits at ~84% relative
# luminance rather than the ~92% it used to, because a near-100% full-field
# emitter is uncomfortable in a dim room. Card-vs-page fill separation is only
# ~1.10:1 at these luminances (too small to perceive on its own), so GRIDLINE
# borders carry the structure, not the fill difference.
#
#   INK_MUTED  4.9:1 on PAGE, 5.4:1 on SURFACE, 4.7:1 on SIDEBAR -- AA everywhere
#   GRIDLINE   1.22:1 on PAGE -- visible enough to bound a card
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#67655f"
GRIDLINE = "#d9d7cf"
SURFACE = "#f8f7f3"
PAGE = "#eeece6"
SIDEBAR = "#e9e7e0"

# Reserved status colours -- never reused as series colours. All four clear
# 3:1 against PAGE (WCAG 1.4.11, graphical objects); `warning` and `serious`
# were darkened from #e0940a/#ec835a, which sat at 2.1:1 and 2.2:1.
STATUS = {
    "good": "#0b9a0b",
    "warning": "#b67706",
    "serious": "#c56c4a",
    "critical": "#d03b3b",
}

# sequential ramps for magnitude encodings (choropleth): one hue, light->dark
SEQ_BLUE = [[0.0, "#eef3fb"], [0.5, "#7fabe3"], [1.0, "#1b4f96"]]
SEQ_GREEN = [[0.0, "#eaf7f1"], [0.5, "#6cc9a4"], [1.0, "#0d7a52"]]
# diverging pair for polarity (negative vs positive growth): warm pole,
# neutral midpoint, cool pole
DIV_AMBER_BLUE = [[0.0, "#b26f00"], [0.5, "#f0efe9"], [1.0, "#1b4f96"]]


def rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def base_layout(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        height=height,
        font=dict(family=FONT, color=INK_SECONDARY, size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(color=INK_SECONDARY), bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=0, r=8, t=34, b=0),
        hovermode="x unified",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=GRIDLINE, font=dict(family=FONT, color=INK_PRIMARY)),
    )
    fig.update_xaxes(showgrid=False, showline=True, linecolor=GRIDLINE, tickfont=dict(color=INK_MUTED))
    fig.update_yaxes(showgrid=True, gridcolor=GRIDLINE, gridwidth=1, zeroline=False, tickfont=dict(color=INK_MUTED))
    return fig


def sparkline(df: pd.DataFrame, key: str, color: str) -> go.Figure:
    tail = df[["date", key]].dropna().tail(24)
    fig = go.Figure(go.Scatter(
        x=tail["date"], y=tail[key],
        mode="lines",
        line=dict(color=color, width=2, shape="spline"),
        fill="tozeroy", fillcolor=rgba(color, 0.08),
        hoverinfo="skip",
    ))
    fig.update_layout(
        height=48, margin=dict(l=0, r=0, t=2, b=0),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", showlegend=False,
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, range=[tail[key].min() * 0.97, tail[key].max() * 1.03] if not tail.empty else None)
    return fig
