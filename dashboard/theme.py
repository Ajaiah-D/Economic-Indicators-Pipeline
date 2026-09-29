"""
Shared design tokens and chart helpers for all dashboard pages.

app.py (national) and states_view.py both import from here so the two pages
stay visually identical without copy-pasted hex codes.
"""

import pandas as pd
import plotly.graph_objects as go

FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"

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
