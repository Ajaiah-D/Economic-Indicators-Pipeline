import io
import os
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Economic Indicators Dashboard",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

LOCAL_DBT_PARQUET = Path(__file__).parent.parent / "dbt" / "target" / "economic_dashboard.parquet"
LOCAL_SNAPSHOT_PARQUET = Path(__file__).parent.parent / "data" / "economic_dashboard.parquet"
S3_PARQUET_KEY = "processed/economic_indicators"

FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"

# -- validated categorical palette (see dataviz skill palette.md), fixed order --
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
SURFACE = "#fcfcfb"

STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

INDICATOR_META = {
    "cpi":                {"label": "CPI",                "unit": "Index (1982-84=100)", "color": "#2a78d6"},
    "unemployment_rate":  {"label": "Unemployment Rate",  "unit": "%",                   "color": "#1baf7a"},
    "gdp":                {"label": "GDP",                "unit": "Billions USD",        "color": "#c98500"},
    "fed_funds_rate":     {"label": "Fed Funds Rate",     "unit": "%",                   "color": "#008300"},
    "housing_starts":     {"label": "Housing Starts",     "unit": "Thousands of Units",  "color": "#4a3aa7"},
    "consumer_sentiment": {"label": "Consumer Sentiment", "unit": "Index",               "color": "#e34948"},
}

FLAG_DESCRIPTIONS = {
    "flag_unemployment_rising": "Unemployment rising",
    "flag_gdp_contracting":     "GDP contracting",
    "flag_inflation_elevated":  "Inflation elevated (>3% annualised)",
    "flag_fed_rate_elevated":   "Fed rate elevated (>4%)",
    "flag_housing_declining":   "Housing starts declining",
    "flag_sentiment_falling":   "Consumer sentiment falling",
}

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
}


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        html, body, [class*="css"] {{
            font-family: {FONT};
        }}
        .block-container {{
            padding-top: 2.25rem;
            padding-bottom: 3rem;
            max-width: 1200px;
        }}
        h1, h2, h3 {{
            font-family: {FONT};
            letter-spacing: -0.01em;
        }}
        .app-title {{
            font-size: 1.9rem;
            font-weight: 650;
            color: {INK_PRIMARY};
            margin-bottom: 0.15rem;
        }}
        .app-caption {{
            color: {INK_SECONDARY};
            font-size: 0.92rem;
            margin-bottom: 1.6rem;
        }}
        .section-label {{
            font-size: 0.78rem;
            font-weight: 600;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            color: {INK_MUTED};
            margin: 0 0 0.6rem 0;
        }}
        div[data-testid="stMetric"] {{
            background: {SURFACE};
            border: 1px solid rgba(11,11,11,0.08);
            border-radius: 10px;
            padding: 0.85rem 1rem 0.6rem 1rem;
        }}
        div[data-testid="stMetricLabel"] {{
            color: {INK_SECONDARY};
        }}
        div[data-testid="stMetricValue"] {{
            color: {INK_PRIMARY};
        }}
        hr {{
            border-color: {GRIDLINE};
        }}
        .status-pill {{
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.28rem 0.75rem;
            border-radius: 999px;
            font-size: 0.82rem;
            font-weight: 600;
        }}
        .status-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
        }}
        .flag-chip {{
            display: flex;
            align-items: center;
            gap: 0.55rem;
            padding: 0.35rem 0;
            font-size: 0.92rem;
            color: {INK_PRIMARY};
        }}
        .flag-chip-dot {{
            width: 8px;
            height: 8px;
            min-width: 8px;
            border-radius: 50%;
            background: {STATUS['critical']};
        }}
        .no-flags {{
            color: {INK_SECONDARY};
            font-size: 0.92rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


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

    # no backend wired up yet -- generate synthetic data so the UI is still usable
    return _demo_data()


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

    for col in INDICATOR_META:
        df[f"{col}_mom_pct"] = df[col].pct_change() * 100
        df[f"{col}_3m_avg"]  = df[col].rolling(3).mean()

    df["flag_unemployment_rising"]  = df["unemployment_rate"].diff(3) > 0
    df["flag_gdp_contracting"]      = df["gdp_mom_pct"] < 0
    df["flag_inflation_elevated"]   = df["cpi"].pct_change(12) * 100 > 3
    df["flag_fed_rate_elevated"]    = df["fed_funds_rate"] > 4
    df["flag_housing_declining"]    = df["housing_starts_mom_pct"] < 0
    df["flag_sentiment_falling"]    = df["consumer_sentiment_mom_pct"] < 0

    flag_cols = list(FLAG_DESCRIPTIONS.keys())
    df["signal_score"]    = df[flag_cols].sum(axis=1)
    df["recession_watch"] = df["signal_score"] >= 3
    return df


def base_layout(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        height=height,
        font=dict(family=FONT, color=INK_SECONDARY, size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color=INK_SECONDARY)),
        margin=dict(l=0, r=0, t=30, b=0),
        hovermode="x unified",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=GRIDLINE, font=dict(family=FONT, color=INK_PRIMARY)),
    )
    fig.update_xaxes(showgrid=False, showline=True, linecolor=GRIDLINE, tickfont=dict(color=INK_MUTED))
    fig.update_yaxes(showgrid=True, gridcolor=GRIDLINE, gridwidth=1, zeroline=False, tickfont=dict(color=INK_MUTED))
    return fig


def sidebar(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    st.sidebar.markdown('<div class="section-label">Controls</div>', unsafe_allow_html=True)

    min_date = df["date"].min().date()
    max_date = df["date"].max().date()

    date_range = st.sidebar.date_input(
        "Date range",
        value=(max(min_date, date(2015, 1, 1)), max_date),
        min_value=min_date,
        max_value=max_date,
    )
    # date_input returns a single-element tuple while the user has only picked
    # the start of the range (before choosing an end date) -- fall back to the
    # current end of data until both dates are selected, rather than crashing.
    if len(date_range) == 2:
        start, end = date_range
    else:
        start, end = date_range[0], max_date

    selected = st.sidebar.multiselect(
        "Indicators to display",
        options=list(INDICATOR_META.keys()),
        default=list(INDICATOR_META.keys()),
        format_func=lambda k: INDICATOR_META[k]["label"],
    )

    mask = (df["date"].dt.date >= start) & (df["date"].dt.date <= end)
    return df[mask].copy(), selected


def sparkline(df: pd.DataFrame, key: str, color: str) -> go.Figure:
    tail = df[["date", key]].dropna().tail(12)
    fig = go.Figure(go.Scatter(
        x=tail["date"], y=tail[key],
        mode="lines",
        line=dict(color=color, width=2, shape="spline"),
        hoverinfo="skip",
    ))
    fig.update_layout(
        height=42,
        margin=dict(l=0, r=0, t=0, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def _kpi_tile(col, df: pd.DataFrame, key: str) -> None:
    meta = INDICATOR_META[key]
    # each series publishes on its own lag (GDP is quarterly, CPI/sentiment
    # trail by weeks) -- use each indicator's own most recent non-null row
    # rather than the last row of the full outer-joined table.
    available = df.dropna(subset=[key])
    as_of = None
    if not available.empty:
        latest_row = available.iloc[-1]
        val = latest_row[key]
        mom = latest_row.get(f"{key}_mom_pct")
        as_of = latest_row["date"]
    else:
        val = mom = None
    with col:
        st.metric(
            label=meta["label"],
            value=f"{val:,.2f}" if pd.notna(val) else "N/A",
            delta=f"{mom:+.2f}% MoM" if pd.notna(mom) else None,
            help=f"As of {as_of:%b %Y}" if as_of is not None else None,
        )
        st.plotly_chart(
            sparkline(df, key, meta["color"]),
            width="stretch",
            config={"displayModeBar": False},
            key=f"spark_{key}",
        )


def kpi_cards(df: pd.DataFrame, selected: list[str]) -> None:
    st.markdown('<div class="section-label">Latest readings</div>', unsafe_allow_html=True)
    # wrap into rows instead of squeezing every tile into one row -- cramming
    # 5-6 tiles side by side truncates the value text.
    for row_start in range(0, len(selected), KPI_TILES_PER_ROW):
        row_keys = selected[row_start:row_start + KPI_TILES_PER_ROW]
        cols = st.columns(KPI_TILES_PER_ROW)
        for col, key in zip(cols, row_keys):
            _kpi_tile(col, df, key)
        for col in cols[len(row_keys):]:
            with col:
                st.empty()


def time_series_chart(df: pd.DataFrame, selected: list[str]) -> None:
    st.markdown('<div class="section-label">Indicator trends over time</div>', unsafe_allow_html=True)

    tabs = st.tabs(["Raw values", "Month-over-month %", "3-month rolling average"])
    variants = [("", ""), ("_mom_pct", " (MoM %)"), ("_3m_avg", " (3-mo avg)")]

    for tab, (suffix, label_suffix) in zip(tabs, variants):
        with tab:
            fig = go.Figure()
            for key in selected:
                col = f"{key}{suffix}"
                if col not in df.columns:
                    continue
                meta = INDICATOR_META[key]
                fig.add_trace(go.Scatter(
                    x=df["date"],
                    y=df[col],
                    name=meta["label"] + label_suffix,
                    mode="lines",
                    line=dict(color=meta["color"], width=2),
                    hovertemplate=f"{meta['label']}: %{{y:.2f}} {meta['unit']}<extra></extra>",
                ))
            fig = base_layout(fig, height=440)
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def status_for_score(score: int, recession_watch: bool) -> tuple[str, str]:
    if recession_watch:
        return STATUS["critical"], "Recession watch"
    if score >= 2:
        return STATUS["warning"], "Elevated"
    return STATUS["good"], "Stable"


def signal_panel(df: pd.DataFrame) -> None:
    st.markdown('<div class="section-label">Economic signals</div>', unsafe_allow_html=True)
    latest = df.iloc[-1]

    active_flags = [FLAG_DESCRIPTIONS[f] for f in FLAG_DESCRIPTIONS if latest.get(f, False)]
    score = int(latest.get("signal_score", 0))
    recession_watch = bool(latest.get("recession_watch", False))
    colour, status_label = status_for_score(score, recession_watch)

    col_score, col_flags = st.columns([1, 2.2])

    with col_score:
        st.markdown(
            f"""
            <div style="text-align:center; padding:22px 16px; border-radius:12px;
                        background:{SURFACE}; border:1px solid rgba(11,11,11,0.08);">
                <div style="font-size:3.2rem; font-weight:650; color:{INK_PRIMARY}; line-height:1;">{score}<span style="font-size:1.4rem; color:{INK_MUTED};">/6</span></div>
                <div style="font-size:0.82rem; color:{INK_SECONDARY}; margin-top:0.3rem;">Signal score</div>
                <div style="margin-top:0.85rem;">
                    <span class="status-pill" style="background:{colour}1a; color:{colour};">
                        <span class="status-dot" style="background:{colour};"></span>{status_label}
                    </span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_flags:
        st.markdown(
            f'<div style="font-size:0.82rem; color:{INK_SECONDARY}; margin-bottom:0.5rem;">Active stress signals</div>',
            unsafe_allow_html=True,
        )
        if active_flags:
            chips = "".join(
                f'<div class="flag-chip"><span class="flag-chip-dot"></span>{flag}</div>'
                for flag in active_flags
            )
            st.markdown(chips, unsafe_allow_html=True)
        else:
            st.markdown('<div class="no-flags">No active stress signals. Economic conditions appear stable.</div>', unsafe_allow_html=True)

    fig = go.Figure(go.Scatter(
        x=df["date"], y=df["signal_score"],
        mode="lines",
        line=dict(color="#2a78d6", width=2),
        fill="tozeroy",
        fillcolor="rgba(42,120,214,0.10)",
        hovertemplate="Signal score: %{y}<extra></extra>",
    ))
    fig.add_hline(y=3, line_dash="dot", line_color=STATUS["critical"], line_width=1,
                  annotation_text="Recession watch threshold", annotation_font=dict(color=INK_MUTED, size=11))
    fig = base_layout(fig, height=220)
    fig.update_yaxes(range=[0, 6], dtick=1)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def flag_heatmap(df: pd.DataFrame) -> None:
    st.markdown('<div class="section-label">Flag history</div>', unsafe_allow_html=True)
    flag_cols = list(FLAG_DESCRIPTIONS.keys())
    heat_df = df[["date"] + flag_cols].copy()
    heat_df[flag_cols] = heat_df[flag_cols].astype(int)
    heat_df = heat_df.set_index("date")[flag_cols]

    z = heat_df.T.values
    y_labels = [FLAG_DESCRIPTIONS[c] for c in flag_cols]

    fig = go.Figure(go.Heatmap(
        z=z,
        x=heat_df.index,
        y=y_labels,
        xgap=1,
        ygap=6,
        showscale=False,
        colorscale=[[0, "#eeede8"], [1, STATUS["critical"]]],
        zmin=0, zmax=1,
        hovertemplate="%{y}<br>%{x|%b %Y}: %{customdata}<extra></extra>",
        customdata=[["Active" if v else "Inactive" for v in row] for row in z],
    ))
    fig.update_layout(
        height=260,
        font=dict(family=FONT, color=INK_SECONDARY, size=12),
        margin=dict(l=0, r=0, t=10, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=False, showline=False, tickfont=dict(color=INK_MUTED))
    fig.update_yaxes(showgrid=False, showline=False, tickfont=dict(color=INK_MUTED), autorange="reversed")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def glossary_section() -> None:
    with st.expander("Glossary: what these indicators mean, and what's historically good vs. bad"):
        for key, entry in GLOSSARY.items():
            meta = INDICATOR_META[key]
            st.markdown(
                f"""
                <div style="display:flex; gap:0.6rem; margin-bottom:1.1rem;">
                    <span class="status-dot" style="background:{meta['color']}; margin-top:0.35rem;"></span>
                    <div>
                        <div style="font-weight:650; color:{INK_PRIMARY};">{meta['label']}</div>
                        <div style="color:{INK_SECONDARY}; font-size:0.9rem; margin-top:0.15rem;">{entry['what']}</div>
                        <div style="color:{INK_MUTED}; font-size:0.85rem; margin-top:0.3rem;">{entry['context']}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown(f'<hr style="border-color:{GRIDLINE}; margin: 0.5rem 0 1.1rem 0;">', unsafe_allow_html=True)
        st.markdown(
            f'<div style="font-weight:650; color:{INK_PRIMARY}; margin-bottom:0.4rem;">Signal score</div>'
            f'<div style="color:{INK_SECONDARY}; font-size:0.9rem;">'
            "Each month, six stress flags are checked (one per indicator above, using the thresholds noted "
            "in its entry). The signal score is simply how many are active at once, 0–6. A score of 3 or "
            "more triggers <b>Recession watch</b>, a heuristic modeled on the simultaneous deterioration "
            "seen ahead of the 2008 and 2020 downturns, not a guarantee of a recession.</div>",
            unsafe_allow_html=True,
        )


def main() -> None:
    inject_css()

    st.markdown('<div class="app-title">U.S. Economic Indicators Dashboard</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="app-caption">Federal Reserve Economic Data (FRED) · '
        'Pipeline: Python → Airflow → Spark → dbt → Streamlit</div>',
        unsafe_allow_html=True,
    )
    glossary_section()

    df = load_data()

    if df.empty:
        st.error("No data available. Check your data source configuration.")
        return

    filtered_df, selected = sidebar(df)

    if not selected:
        st.warning("Select at least one indicator in the sidebar.")
        return

    kpi_cards(filtered_df, selected)
    st.divider()
    time_series_chart(filtered_df, selected)
    st.divider()
    signal_panel(filtered_df)
    st.divider()
    flag_heatmap(filtered_df)

    with st.expander("Raw data table"):
        st.dataframe(
            filtered_df.sort_values("date", ascending=False).reset_index(drop=True),
            width="stretch",
        )


if __name__ == "__main__":
    main()
