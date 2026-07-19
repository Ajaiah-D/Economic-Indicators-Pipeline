import io
import json
import os
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from plotly.subplots import make_subplots

import revisions_view
import states_view
from briefing import build_briefing
from theme import (
    FONT,
    GRIDLINE,
    INK_MUTED,
    INK_PRIMARY,
    INK_SECONDARY,
    PAGE,
    STATUS,
    SURFACE,
    base_layout,
    rgba as _rgba,
    sparkline,
)

load_dotenv()

st.set_page_config(
    page_title="U.S. Economic Indicators",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

REPO_ROOT = Path(__file__).parent.parent
LOCAL_DBT_PARQUET = REPO_ROOT / "dbt" / "target" / "economic_dashboard.parquet"
LOCAL_SNAPSHOT_PARQUET = REPO_ROOT / "data" / "economic_dashboard.parquet"
LAST_UPDATED_JSON = REPO_ROOT / "data" / "last_updated.json"
S3_PARQUET_KEY = "processed/economic_indicators"

INDICATOR_META = {
    "cpi":                {"label": "CPI",                "short": "CPI",        "unit": "Index (1982-84=100)", "fmt": "{:,.1f}", "color": "#2a78d6"},
    "unemployment_rate":  {"label": "Unemployment Rate",  "short": "Unemp.",     "unit": "%",                   "fmt": "{:,.1f}%", "color": "#1baf7a"},
    "gdp":                {"label": "GDP",                "short": "GDP",        "unit": "Billions USD",        "fmt": "${:,.0f}B", "color": "#c98500"},
    "fed_funds_rate":     {"label": "Fed Funds Rate",     "short": "Fed Funds",  "unit": "%",                   "fmt": "{:,.2f}%", "color": "#008300"},
    "housing_starts":     {"label": "Housing Starts",     "short": "Housing",    "unit": "Thousands of units",  "fmt": "{:,.0f}K", "color": "#4a3aa7"},
    "consumer_sentiment": {"label": "Consumer Sentiment", "short": "Sentiment",  "unit": "Index",               "fmt": "{:,.1f}", "color": "#e34948"},
    "yield_spread":       {"label": "10Y-3M Treasury Spread", "short": "Yield Spread", "unit": "points",       "fmt": "{:+.2f}pt", "color": "#e87ba4"},
}

FLAG_DESCRIPTIONS = {
    "flag_unemployment_rising": "Unemployment rising",
    "flag_gdp_contracting":     "GDP contracting",
    "flag_inflation_elevated":  "Inflation elevated (>3% annualised)",
    "flag_fed_rate_elevated":   "Fed rate elevated vs its 3-year average",
    "flag_housing_declining":   "Housing starts declining",
    "flag_sentiment_falling":   "Consumer sentiment falling",
    "flag_yield_curve_inverted": "Yield curve inverted",
}

# monthly level series -- a month is "complete" once these have published. GDP
# is quarterly and publishes late, so it's deliberately not in this list.
MONTHLY_CORE = ["cpi", "unemployment_rate", "housing_starts", "consumer_sentiment"]

KPI_TILES_PER_ROW = 3

GLOSSARY = {
    "cpi": {
        "what": "The Consumer Price Index tracks the average price of a fixed basket of goods and services, the standard measure of U.S. inflation.",
        "context": "Historically healthy: rising ~2%/yr, the Fed's long-run target. Watch for: annualised increases above ~3-4% (overheating/inflation risk) or an outright decline (deflation, usually a sign of collapsing demand).",
    },
    "unemployment_rate": {
        "what": "The U-3 unemployment rate: the share of the labor force that is jobless and actively looking for work.",
        "context": "Historically healthy: roughly 3.5-4.5% is considered \"full employment.\" Watch for: a rate climbing above ~6% signals real economic slack; the trend matters more than the level, since a rise of 0.5pp or more off its recent low (the \"Sahm rule\") has reliably flagged past recessions.",
    },
    "gdp": {
        "what": "Gross Domestic Product: the total dollar value of goods and services produced in the U.S., reported quarterly.",
        "context": "Historically healthy: steady growth around 2-3% annualised. Watch for: two consecutive quarters of contraction is the textbook definition of a recession; a sharp deceleration is itself a warning sign even before it turns negative.",
    },
    "fed_funds_rate": {
        "what": "The effective federal funds rate: the interest rate the Federal Reserve targets for overnight bank lending, its primary lever for monetary policy.",
        "context": "Low rates (~0-2%) are stimulative and typical during downturns or recovery. High rates (>4-5%) are restrictive, intended to cool inflation, but they raise the risk of tipping the economy into recession the longer they stay elevated.",
    },
    "housing_starts": {
        "what": "The number of new privately-owned residential construction projects started, reported as an annualised rate in thousands of units.",
        "context": "Historically healthy: roughly 1.2-1.5 million units/year. Watch for: sharp declines, since housing is one of the most interest-rate-sensitive sectors and often leads the broader economy into (and out of) a downturn.",
    },
    "consumer_sentiment": {
        "what": "The University of Michigan Consumer Sentiment Index: a survey-based gauge of how confident U.S. consumers feel about their finances and the economy.",
        "context": "Historically healthy: readings above ~90. Watch for: sustained readings below ~70 have historically coincided with recessions, since falling confidence tends to precede pullbacks in consumer spending.",
    },
    "yield_spread": {
        "what": "The 10-year Treasury yield minus the 3-month Treasury yield. Normally long-term rates sit above short-term rates; when that flips negative (an \"inverted\" yield curve), it means investors expect the Fed to cut rates in response to a weakening economy.",
        "context": "Historically healthy: positive, usually 1-2 points. Watch for: a meaningfully negative spread, which has preceded every U.S. recession since the 1960s and is widely considered the single most reliable recession indicator in economics, though it can lead by anywhere from several months to over a year.",
    },
}


# --------------------------------------------------------------------------- #
# Styling
# --------------------------------------------------------------------------- #
def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .stApp {{ background: {PAGE}; }}
        html, body, [class*="css"] {{ font-family: {FONT}; }}
        .block-container {{
            padding-top: 2.4rem;
            padding-bottom: 3rem;
            max-width: 1240px;
        }}
        footer {{ visibility: hidden; }}
        header[data-testid="stHeader"] {{ background: transparent; }}
        h1, h2, h3 {{ font-family: {FONT}; letter-spacing: -0.02em; }}

        /* wide enough for the date-range preset row; buttons wrap, never clip */
        section[data-testid="stSidebar"] {{
            width: 350px !important;
            min-width: 350px !important;
        }}
        div[data-testid="stButtonGroup"] {{
            flex-wrap: wrap;
            gap: 4px;
        }}

        .hero-title {{
            font-size: 2.15rem;
            font-weight: 680;
            color: {INK_PRIMARY};
            margin-bottom: 0.2rem;
            line-height: 1.1;
        }}
        .hero-sub {{
            color: {INK_SECONDARY};
            font-size: 0.98rem;
            margin-bottom: 0.55rem;
        }}
        .hero-meta {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            color: {INK_MUTED};
            font-size: 0.82rem;
        }}
        .live-dot {{
            width: 7px; height: 7px; border-radius: 50%;
            background: {STATUS['good']}; display: inline-block;
            box-shadow: 0 0 0 3px {STATUS['good']}22;
        }}

        .section-label {{
            font-size: 0.76rem;
            font-weight: 650;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: {INK_MUTED};
            margin: 0.2rem 0 0.7rem 0;
        }}

        /* bordered stat-tile containers */
        div[data-testid="stVerticalBlockBorderWrapper"] {{
            background: {SURFACE};
            border-radius: 14px;
        }}
        div[data-testid="stMetric"] {{
            background: transparent;
            border: none;
            padding: 0.1rem 0.2rem 0 0.2rem;
        }}
        div[data-testid="stMetricLabel"] p {{
            font-size: 0.86rem;
            font-weight: 600;
            color: {INK_SECONDARY};
        }}
        div[data-testid="stMetricValue"] {{
            font-size: 1.9rem;
            font-weight: 640;
            color: {INK_PRIMARY};
        }}
        .tile-asof {{
            font-size: 0.72rem;
            color: {INK_MUTED};
            margin: 0.1rem 0 0.2rem 0.2rem;
        }}

        /* signal banner */
        .banner {{
            border-radius: 16px;
            padding: 1.25rem 1.4rem;
            border: 1px solid rgba(11,11,11,0.06);
            box-shadow: 0 1px 2px rgba(11,11,11,0.04);
        }}
        .banner-score {{ font-size: 3.4rem; font-weight: 680; line-height: 1; }}
        .banner-score small {{ font-size: 1.3rem; color: {INK_MUTED}; font-weight: 500; }}
        .status-pill {{
            display: inline-flex; align-items: center; gap: 0.45rem;
            padding: 0.3rem 0.85rem; border-radius: 999px;
            font-size: 0.86rem; font-weight: 650;
        }}
        .status-dot {{ width: 9px; height: 9px; border-radius: 50%; display: inline-block; }}
        .flag-chip {{
            display: inline-flex; align-items: center; gap: 0.5rem;
            padding: 0.4rem 0.7rem; margin: 0 0.4rem 0.4rem 0;
            background: {SURFACE}; border: 1px solid rgba(208,59,59,0.25);
            border-radius: 8px; font-size: 0.88rem; color: {INK_PRIMARY};
        }}
        .flag-chip-dot {{ width: 7px; height: 7px; border-radius: 50%; background: {STATUS['critical']}; }}
        .all-clear {{
            display: inline-flex; align-items: center; gap: 0.5rem;
            padding: 0.4rem 0.75rem; background: {SURFACE};
            border: 1px solid rgba(12,163,12,0.28); border-radius: 8px;
            font-size: 0.9rem; color: {INK_PRIMARY};
        }}

        /* monthly briefing */
        .brief-card {{
            background: {SURFACE};
            border: 1px solid {GRIDLINE};
            border-radius: 16px;
            padding: 1.1rem 1.3rem 1.2rem 1.3rem;
            box-shadow: 0 1px 2px rgba(11,11,11,0.04);
        }}
        .brief-head {{ display: flex; align-items: baseline; gap: 0.6rem; margin-bottom: 0.65rem; flex-wrap: wrap; }}
        .brief-title {{ font-weight: 680; font-size: 1.02rem; color: {INK_PRIMARY}; }}
        .brief-vs {{ color: {INK_MUTED}; font-size: 0.78rem; }}
        .brief-item {{
            display: flex; gap: 0.6rem; align-items: flex-start;
            margin: 0.42rem 0; color: {INK_SECONDARY};
            font-size: 0.92rem; line-height: 1.55;
        }}
        .brief-item strong {{ color: {INK_PRIMARY}; font-weight: 650; }}
        .brief-dot {{ width: 8px; height: 8px; border-radius: 50%; flex: none; margin-top: 0.48rem; }}
        .brief-quiet {{ color: {INK_MUTED}; font-size: 0.84rem; margin-top: 0.55rem; }}

        .footer {{
            margin-top: 2.5rem; padding-top: 1rem;
            border-top: 1px solid {GRIDLINE};
            color: {INK_MUTED}; font-size: 0.8rem;
            display: flex; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem;
        }}
        .footer a {{ color: {INK_SECONDARY}; text-decoration: none; }}
        div[data-testid="stExpander"] details {{
            border: 1px solid {GRIDLINE}; border-radius: 12px; background: {SURFACE};
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=3600, show_spinner="Loading economic data...")
def load_data() -> pd.DataFrame:
    # a local dbt build takes priority (a dev who just ran `dbt run` sees
    # their own fresh output); the committed snapshot is what a deployed
    # app (e.g. Streamlit Community Cloud) actually has, refreshed daily by
    # .github/workflows/refresh_data.yml
    for local_path in (LOCAL_DBT_PARQUET, LOCAL_SNAPSHOT_PARQUET):
        if local_path.exists():
            df = pd.read_parquet(local_path)
            df["date"] = pd.to_datetime(df["date"])
            return df.sort_values("date")

    bucket = os.environ.get("AWS_BUCKET_NAME")
    if bucket:
        import boto3
        s3 = boto3.client(
            "s3",
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
        obj = s3.get_object(Bucket=bucket, Key=f"{S3_PARQUET_KEY}/part-0.parquet")
        df = pd.read_parquet(io.BytesIO(obj["Body"].read()))
        df["date"] = pd.to_datetime(df["date"])
        return df.sort_values("date")

    return _demo_data()


@st.cache_data(ttl=3600)
def load_metadata() -> dict:
    if LAST_UPDATED_JSON.exists():
        try:
            return json.loads(LAST_UPDATED_JSON.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _demo_data() -> pd.DataFrame:
    import numpy as np

    rng = pd.date_range("2010-01-01", periods=168, freq="MS")
    np.random.seed(42)

    def rand_walk(start, drift, vol, n):
        return start + np.cumsum(np.random.normal(drift, vol, n))

    df = pd.DataFrame({"date": rng})
    df["cpi"]                = rand_walk(215, 0.3, 0.5, len(rng))
    df["unemployment_rate"]  = np.clip(rand_walk(6.5, -0.02, 0.2, len(rng)), 2, 15)
    df["gdp"]                = rand_walk(15000, 50, 80, len(rng))
    df["fed_funds_rate"]     = np.clip(rand_walk(2, 0.01, 0.15, len(rng)), 0, 8)
    df["housing_starts"]     = np.clip(rand_walk(1200, 0, 50, len(rng)), 500, 2000)
    df["consumer_sentiment"] = np.clip(rand_walk(80, 0, 3, len(rng)), 40, 110)
    df["yield_spread"]       = np.clip(rand_walk(1.5, 0, 0.25, len(rng)), -2, 4)

    for col in INDICATOR_META:
        df[f"{col}_mom_pct"] = df[col].pct_change() * 100
        df[f"{col}_3m_avg"]  = df[col].rolling(3).mean()

    df["flag_unemployment_rising"]   = df["unemployment_rate_3m_avg"] > df["unemployment_rate_3m_avg"].shift(3)
    df["flag_gdp_contracting"]       = df["gdp_mom_pct"] < 0
    df["flag_inflation_elevated"]    = df["cpi"].pct_change(12) * 100 > 3
    df["flag_fed_rate_elevated"]     = df["fed_funds_rate"] > df["fed_funds_rate"].rolling(36, min_periods=24).mean() + 1.0
    df["flag_housing_declining"]     = df["housing_starts_3m_avg"] < df["housing_starts_3m_avg"].shift(3)
    df["flag_sentiment_falling"]     = df["consumer_sentiment_3m_avg"] < df["consumer_sentiment_3m_avg"].shift(3)
    df["flag_yield_curve_inverted"]  = df["yield_spread"] < -0.25

    flag_cols = list(FLAG_DESCRIPTIONS.keys())
    df["signal_score"]    = df[flag_cols].sum(axis=1)
    df["recession_watch"] = df["signal_score"] >= 4
    return df


def latest_complete_row(df: pd.DataFrame) -> pd.Series:
    # the signal score is only meaningful for a month whose monthly indicators
    # have actually published. Reading the raw last row shows an artificially
    # calm score because the newest month is still half-empty (publish lag).
    complete = df.dropna(subset=[c for c in MONTHLY_CORE if c in df.columns])
    return complete.iloc[-1] if not complete.empty else df.iloc[-1]


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #
def header(df: pd.DataFrame, meta: dict) -> None:
    data_through = df["date"].max()
    through_str = data_through.strftime("%b %Y") if pd.notna(data_through) else "n/a"

    updated_str = ""
    ts = meta.get("last_updated_utc")
    if ts:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            updated_str = dt.strftime("%b %d, %Y")
        except ValueError:
            updated_str = ""

    meta_bits = f"Data through {through_str}"
    if updated_str:
        meta_bits += f" &nbsp;·&nbsp; Auto-refreshed daily &nbsp;·&nbsp; Last update {updated_str}"

    st.markdown(
        f"""
        <div class="hero-title">U.S. Economic Indicators</div>
        <div class="hero-sub">Federal Reserve (FRED) macro indicators and Treasury yields, with a composite recession-risk signal.</div>
        <div class="hero-meta"><span class="live-dot"></span>{meta_bits}</div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")


def status_for_score(score: int, recession_watch: bool) -> tuple[str, str]:
    if recession_watch:
        return STATUS["critical"], "Recession watch"
    if score >= 3:
        return STATUS["warning"], "Elevated risk"
    return STATUS["good"], "Stable"


def signal_banner(df: pd.DataFrame) -> None:
    row = latest_complete_row(df)
    score = int(row.get("signal_score", 0))
    recession_watch = bool(row.get("recession_watch", False))
    colour, label = status_for_score(score, recession_watch)
    as_of = row["date"].strftime("%b %Y") if pd.notna(row["date"]) else ""
    active = [FLAG_DESCRIPTIONS[f] for f in FLAG_DESCRIPTIONS if bool(row.get(f, False))]

    left, right = st.columns([1, 2.3], gap="medium")

    with left:
        st.markdown(
            f"""
            <div class="banner" style="background:{_rgba(colour, 0.06)}; border-color:{_rgba(colour, 0.25)};">
                <div style="color:{INK_MUTED}; font-size:0.76rem; font-weight:650; letter-spacing:0.08em; text-transform:uppercase;">Recession-risk signal</div>
                <div class="banner-score" style="color:{INK_PRIMARY}; margin-top:0.35rem;">{score}<small>/7</small></div>
                <div style="margin-top:0.6rem;">
                    <span class="status-pill" style="background:{_rgba(colour, 0.14)}; color:{colour};">
                        <span class="status-dot" style="background:{colour};"></span>{label}
                    </span>
                </div>
                <div style="color:{INK_MUTED}; font-size:0.76rem; margin-top:0.7rem;">as of {as_of}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        st.markdown('<div class="section-label" style="margin-top:0.2rem;">Active stress signals</div>', unsafe_allow_html=True)
        if active:
            chips = "".join(
                f'<span class="flag-chip"><span class="flag-chip-dot"></span>{f}</span>' for f in active
            )
            st.markdown(f"<div>{chips}</div>", unsafe_allow_html=True)
        else:
            st.markdown(
                f'<span class="all-clear"><span class="status-dot" style="background:{STATUS["good"]};"></span>'
                'No active stress signals. Conditions appear stable.</span>',
                unsafe_allow_html=True,
            )
        st.markdown(
            f'<div style="color:{INK_MUTED}; font-size:0.8rem; margin-top:0.85rem; line-height:1.5;">'
            "The score counts how many of seven stress conditions are active at once, including an "
            "inverted yield curve. A reading of 4 or more trips the recession-watch threshold. "
            "Backtested against every NBER recession since 1959: it catches all 9, with about 44% "
            "of flagged months turning out to be false alarms (not a forecast).</div>",
            unsafe_allow_html=True,
        )


def briefing_section(df: pd.DataFrame) -> None:
    # always fed the full history: superlatives ("lowest since 2009") are
    # meaningless when the comparison window is whatever range the sidebar
    # happens to be filtered to
    b = build_briefing(df)
    if b is None:
        return
    st.markdown('<div class="section-label">This month in brief</div>', unsafe_allow_html=True)
    tone_colors = {"warn": STATUS["warning"], "good": STATUS["good"], "neutral": INK_MUTED}
    rows = "".join(
        f'<div class="brief-item"><span class="brief-dot" style="background:{tone_colors[item.tone]};"></span>'
        f"<span>{item.text}</span></div>"
        for item in [b.score_item] + b.items
    )
    quiet_html = ""
    if b.quiet:
        names = b.quiet[0] if len(b.quiet) == 1 else ", ".join(b.quiet[:-1]) + " and " + b.quiet[-1]
        quiet_html = f'<div class="brief-quiet">Little change in {names}.</div>'
    st.markdown(
        f"""
        <div class="brief-card">
            <div class="brief-head">
                <span class="brief-title">{b.latest_label}</span>
                <span class="brief-vs">vs {b.previous_label} &nbsp;·&nbsp; written automatically from each data refresh</span>
            </div>
            {rows}
            {quiet_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _kpi_tile(df: pd.DataFrame, key: str) -> None:
    # renders directly into the caller's current container context.
    meta = INDICATOR_META[key]
    available = df.dropna(subset=[key])
    if not available.empty:
        r = available.iloc[-1]
        mom = r.get(f"{key}_mom_pct")
        as_of = r["date"].strftime("%b %Y")
        value_str = meta["fmt"].format(r[key])
    else:
        mom = None
        as_of = ""
        value_str = "N/A"

    st.metric(
        label=meta["label"],
        value=value_str,
        delta=f"{mom:+.2f}% MoM" if pd.notna(mom) else None,
    )
    st.markdown(f'<div class="tile-asof">as of {as_of}</div>', unsafe_allow_html=True)
    st.plotly_chart(
        sparkline(df, key, meta["color"]),
        width="stretch",
        config={"displayModeBar": False},
        key=f"spark_{key}",
    )


def kpi_grid(df: pd.DataFrame, selected: list[str]) -> None:
    st.markdown('<div class="section-label">Latest readings</div>', unsafe_allow_html=True)
    for row_start in range(0, len(selected), KPI_TILES_PER_ROW):
        row_keys = selected[row_start:row_start + KPI_TILES_PER_ROW]
        cols = st.columns(KPI_TILES_PER_ROW, gap="medium")
        for col, key in zip(cols, row_keys):
            with col.container(border=True):
                _kpi_tile(df, key)
        for col in cols[len(row_keys):]:
            col.empty()


def trends(df: pd.DataFrame, selected: list[str]) -> None:
    st.markdown('<div class="section-label">Indicator trends</div>', unsafe_allow_html=True)
    tab_levels, tab_mom = st.tabs(["Levels", "Month-over-month %"])

    with tab_levels:
        st.caption(
            "Actual values over the selected range. Each indicator has its own panel and scale, since they "
            "are measured in very different units (an index, a percent, billions of dollars)."
        )
        n = len(selected)
        cols_n = 1 if n == 1 else 2
        rows_n = (n + cols_n - 1) // cols_n
        fig = make_subplots(
            rows=rows_n, cols=cols_n,
            subplot_titles=[INDICATOR_META[k]["label"] for k in selected],
            vertical_spacing=0.16 if rows_n > 1 else 0.1,
            horizontal_spacing=0.09,
        )
        for i, key in enumerate(selected):
            r, c = i // cols_n + 1, i % cols_n + 1
            meta = INDICATOR_META[key]
            s = df[["date", key]].dropna()
            fig.add_trace(
                go.Scatter(
                    x=s["date"], y=s[key], mode="lines", name=meta["label"],
                    line=dict(color=meta["color"], width=2),
                    fill="tozeroy", fillcolor=_rgba(meta["color"], 0.06),
                    hovertemplate=f"%{{x|%b %Y}} &nbsp; %{{y:,.1f}} {meta['unit']}<extra></extra>",
                ),
                row=r, col=c,
            )
        fig.update_layout(
            height=210 * rows_n + 30,
            showlegend=False,
            font=dict(family=FONT, color=INK_SECONDARY, size=12),
            margin=dict(l=0, r=8, t=30, b=0),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            hoverlabel=dict(bgcolor=SURFACE, bordercolor=GRIDLINE, font=dict(family=FONT, color=INK_PRIMARY)),
        )
        fig.update_xaxes(showgrid=False, showline=True, linecolor=GRIDLINE, tickfont=dict(color=INK_MUTED, size=11))
        fig.update_yaxes(showgrid=True, gridcolor=GRIDLINE, zeroline=False, tickfont=dict(color=INK_MUTED, size=11))
        for ann in fig.layout.annotations:  # subplot titles
            ann.font.update(size=13, color=INK_PRIMARY)
            ann.update(x=ann.x, xanchor="center")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    with tab_mom:
        st.caption("Month-over-month percent change. Already on a common scale, so all series share one axis.")
        fig = go.Figure()
        for key in selected:
            col = f"{key}_mom_pct"
            if col not in df.columns:
                continue
            meta = INDICATOR_META[key]
            s = df[["date", col]].dropna()
            fig.add_trace(go.Scatter(
                x=s["date"], y=s[col],
                name=meta["label"], mode="lines",
                line=dict(color=meta["color"], width=2),
                hovertemplate=f"{meta['label']}: %{{y:+.2f}}%<extra></extra>",
            ))
        fig.add_hline(y=0, line_color=INK_MUTED, line_width=1)
        fig = base_layout(fig, height=430)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def signal_history(df: pd.DataFrame) -> None:
    st.markdown('<div class="section-label">Signal history</div>', unsafe_allow_html=True)

    fig = go.Figure(go.Scatter(
        x=df["date"], y=df["signal_score"], mode="lines",
        line=dict(color="#2a78d6", width=2, shape="hv"),
        fill="tozeroy", fillcolor="rgba(42,120,214,0.10)",
        hovertemplate="Signal score: %{y} of 7<extra></extra>",
    ))
    fig.add_hline(y=4, line_dash="dot", line_color=STATUS["critical"], line_width=1.5,
                  annotation_text="Recession-watch threshold",
                  annotation_position="top left",
                  annotation_font=dict(color=STATUS["critical"], size=11))
    fig = base_layout(fig, height=230)
    fig.update_yaxes(range=[0, 7.3], dtick=1)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    flag_cols = list(FLAG_DESCRIPTIONS.keys())
    heat = df[["date"] + flag_cols].copy()
    heat[flag_cols] = heat[flag_cols].astype(int)
    heat = heat.set_index("date")[flag_cols]
    z = heat.T.values

    fig2 = go.Figure(go.Heatmap(
        z=z, x=heat.index, y=[FLAG_DESCRIPTIONS[c] for c in flag_cols],
        xgap=0, ygap=5, showscale=False,
        colorscale=[[0, "#efeee9"], [1, STATUS["critical"]]],
        zmin=0, zmax=1,
        hovertemplate="%{y}<br>%{x|%b %Y}: %{customdata}<extra></extra>",
        customdata=[["Active" if v else "Inactive" for v in row] for row in z],
    ))
    fig2.update_layout(
        height=250, font=dict(family=FONT, color=INK_SECONDARY, size=12),
        margin=dict(l=0, r=8, t=6, b=0),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    )
    fig2.update_xaxes(showgrid=False, showline=False, tickfont=dict(color=INK_MUTED))
    fig2.update_yaxes(showgrid=False, showline=False, tickfont=dict(color=INK_MUTED, size=11), autorange="reversed")
    st.plotly_chart(fig2, width="stretch", config={"displayModeBar": False})


def glossary_section() -> None:
    with st.expander("Glossary: what each indicator means, and what's historically good vs. bad"):
        for key, entry in GLOSSARY.items():
            meta = INDICATOR_META[key]
            st.markdown(
                f"""
                <div style="display:flex; gap:0.7rem; margin-bottom:1.1rem;">
                    <span style="width:9px; height:9px; border-radius:50%; background:{meta['color']}; margin-top:0.4rem; flex:none;"></span>
                    <div>
                        <div style="font-weight:660; color:{INK_PRIMARY};">{meta['label']}</div>
                        <div style="color:{INK_SECONDARY}; font-size:0.9rem; margin-top:0.15rem; line-height:1.5;">{entry['what']}</div>
                        <div style="color:{INK_MUTED}; font-size:0.85rem; margin-top:0.3rem; line-height:1.5;">{entry['context']}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def footer() -> None:
    st.markdown(
        f"""
        <div class="footer">
            <span>Source: Federal Reserve Economic Data (FRED), St. Louis Fed</span>
            <span>Pipeline: Python &rarr; Airflow &rarr; dbt &rarr; Streamlit &nbsp;·&nbsp; refreshed daily via GitHub Actions</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Sidebar + main
# --------------------------------------------------------------------------- #
# quick ranges are anchored to the newest date in the data, not today --
# FRED series trail the calendar by weeks, so "last 6 months" should mean
# the 6 months ending at the last observation.
RANGE_PRESETS = {"6M": 6, "1Y": 12, "2Y": 24, "5Y": 60, "10Y": 120, "All": None}


def sidebar(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    st.sidebar.markdown('<div class="section-label">Filters</div>', unsafe_allow_html=True)

    min_date = df["date"].min().date()
    max_date = df["date"].max().date()

    choice = st.sidebar.segmented_control(
        "Date range",
        options=list(RANGE_PRESETS) + ["Custom"],
        default="10Y",
    )
    if not choice:  # segmented control deselects on second click
        choice = "All"

    if choice == "Custom":
        date_range = st.sidebar.date_input(
            "Custom range",
            value=(max(min_date, date(2015, 1, 1)), max_date),
            min_value=min_date,
            max_value=max_date,
        )
        if len(date_range) == 2:
            start, end = date_range
        else:
            start, end = date_range[0], max_date
    else:
        end = max_date
        months = RANGE_PRESETS[choice]
        if months is None:
            start = min_date
        else:
            start = max(min_date, (pd.Timestamp(end) - pd.DateOffset(months=months)).date())

    st.sidebar.caption(f"Showing {start:%b %Y} – {end:%b %Y}")
    st.sidebar.write("")
    selected = st.sidebar.multiselect(
        "Indicators",
        options=list(INDICATOR_META.keys()),
        default=list(INDICATOR_META.keys()),
        format_func=lambda k: INDICATOR_META[k]["label"],
    )

    mask = (df["date"].dt.date >= start) & (df["date"].dt.date <= end)
    return df[mask].copy(), selected


def national_page() -> None:
    df = load_data()
    meta = load_metadata()

    if df.empty:
        st.error("No data available. Check your data source configuration.")
        return

    filtered_df, selected = sidebar(df)

    header(df, meta)

    if filtered_df.empty:
        st.warning("No data in the selected date range.")
        return

    signal_banner(filtered_df)
    st.write("")
    briefing_section(df)
    st.divider()

    if not selected:
        st.warning("Select at least one indicator in the sidebar to see readings and trends.")
    else:
        kpi_grid(filtered_df, selected)
        st.divider()
        trends(filtered_df, selected)
        st.divider()

    signal_history(filtered_df)
    st.write("")
    glossary_section()

    with st.expander("Raw data table"):
        st.dataframe(
            filtered_df.sort_values("date", ascending=False).reset_index(drop=True),
            width="stretch",
        )

    footer()


def states_page() -> None:
    states_view.render(load_data())
    footer()


def revisions_page() -> None:
    revisions_view.render()
    footer()


def main() -> None:
    inject_css()
    nav = st.navigation([
        st.Page(national_page, title="National overview", url_path="national", default=True),
        st.Page(states_page, title="State by state", url_path="states"),
        st.Page(revisions_page, title="Data revisions", url_path="revisions"),
    ])
    nav.run()


if __name__ == "__main__":
    main()
