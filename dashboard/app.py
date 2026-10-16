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
import theme
import ui
from briefing import build_briefing
from theme import FONT, PLOTLY_CONFIG, plotly_layout, rgba

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

# Series colours come from theme.SERIES by "slot" (one validated palette per
# mode; see theme.py). Slots follow this dict's order.
INDICATOR_META = {
    "cpi":                {"label": "CPI",                "short": "CPI",        "unit": "Index (1982-84=100)", "fmt": "{:,.1f}", "slot": 0},
    "unemployment_rate":  {"label": "Unemployment Rate (U-3)", "short": "Unemp. (U-3)", "unit": "%",              "fmt": "{:,.1f}%", "slot": 1},
    "u6_rate":            {"label": "Unemployment Rate (U-6)", "short": "Unemp. (U-6)", "unit": "%",              "fmt": "{:,.1f}%", "slot": 2},
    "gdp":                {"label": "GDP",                "short": "GDP",        "unit": "Billions USD",        "fmt": "${:,.0f}B", "slot": 3},
    "fed_funds_rate":     {"label": "Fed Funds Rate",     "short": "Fed Funds",  "unit": "%",                   "fmt": "{:,.2f}%", "slot": 4},
    "housing_starts":     {"label": "Housing Starts",     "short": "Housing",    "unit": "Thousands of units",  "fmt": "{:,.0f}K", "slot": 5},
    "consumer_sentiment": {"label": "Consumer Sentiment", "short": "Sentiment",  "unit": "Index",               "fmt": "{:,.1f}", "slot": 6},
    "yield_spread":       {"label": "10Y-3M Treasury Spread", "short": "Yield Spread", "unit": "points",       "fmt": "{:+.2f}pt", "slot": 7},
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
MONTHLY_CORE = ["cpi", "unemployment_rate", "u6_rate", "housing_starts", "consumer_sentiment"]

KPI_TILES_PER_ROW = 3

GLOSSARY = {
    "cpi": {
        "what": "The Consumer Price Index tracks the average price of a fixed basket of goods and services, the standard measure of U.S. inflation.",
        "context": "Historically healthy: rising ~2%/yr, the Fed's long-run target. Watch for: annualised increases above ~3-4% (overheating/inflation risk) or an outright decline (deflation, usually a sign of collapsing demand).",
    },
    "unemployment_rate": {
        "what": "The U-3 unemployment rate: the share of the labor force that is jobless and actively looking for work. This is the headline figure quoted in most news coverage and used as the Fed's standard labor-market benchmark.",
        "context": "Historically healthy: roughly 3.5-4.5% is considered \"full employment.\" Watch for: a rate climbing above ~6% signals real economic slack; the trend matters more than the level, since a rise of 0.5pp or more off its recent low (the \"Sahm rule\") has reliably flagged past recessions. U-3 excludes discouraged workers who've stopped looking and people stuck in part-time work who want full-time hours -- see U-6 for a broader measure of that slack.",
    },
    "u6_rate": {
        "what": "The U-6 unemployment rate: U-3 plus discouraged/marginally attached workers (want a job, looked in the past year, but not the past 4 weeks) and people working part-time only because they can't find full-time work. The broadest of BLS's six official unemployment measures (U-1 through U-6).",
        "context": "Historically healthy: roughly 7-8% in a strong labor market, since it always runs above U-3 (typically by 3.5-4.5 points). Watch for: the gap between U-6 and U-3 widening is itself a signal -- it means underemployment (involuntary part-time, discouraged workers) is growing even if the headline rate looks stable.",
    },
    "gdp": {
        "what": "Gross Domestic Product: the total dollar value of goods and services produced in the U.S., reported quarterly. This is nominal GDP (current dollars, not adjusted for inflation).",
        "context": "Historically healthy: nominal GDP (the series used here, in current dollars) growing roughly 1-1.5% per quarter, which is about 2-3% real growth plus inflation. Watch for: two consecutive quarters of contraction is the textbook definition of a recession; a sharp deceleration is itself a warning sign even before it turns negative.",
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
# Data
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=3600, show_spinner="Loading economic data...")
def load_data() -> pd.DataFrame:
    # a local dbt build takes priority (a dev who just ran `dbt build` sees
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
    # U-6 always sits above U-3 (it's a superset); model it as U-3 plus a
    # noisy spread rather than an independent walk so the two never invert
    df["u6_rate"]            = df["unemployment_rate"] + np.clip(rand_walk(4.0, 0, 0.15, len(rng)), 2, 10)
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
SIGNAL_NOTE = (
    "The score counts how many of seven stress conditions are active at once, including an "
    "inverted yield curve. A reading of 4 or more trips the recession-watch threshold. "
    "Backtested against every NBER recession since 1959: it catches all 9, with about 43% "
    "of flagged months turning out to be false alarms (not a forecast)."
)
FOOTER_SOURCE = "Source: Federal Reserve Economic Data (FRED), St. Louis Fed"
FOOTER_PIPELINE = "Pipeline: Python → Airflow → dbt → Streamlit · refreshed daily via GitHub Actions"


def apply_theme() -> None:
    # style-only st.html goes to Streamlit's event container, so it takes no
    # room on the page; the CSS carries both modes (see ui.build_css)
    st.html(ui.build_css(theme.mode()))


def updated_label(meta: dict) -> str:
    ts = meta.get("last_updated_utc")
    if not ts:
        return ""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%b %d, %Y")
    except ValueError:
        return ""


def source_line(source: str, meta: dict) -> str:
    updated = updated_label(meta)
    return f"Source: {source}" + (f" · Data last changed {updated}" if updated else "")


def header(df: pd.DataFrame, meta: dict) -> None:
    data_through = df["date"].max()
    through_str = data_through.strftime("%b %Y") if pd.notna(data_through) else "n/a"
    bits = [f"Data through {through_str}"]
    updated = updated_label(meta)
    if updated:
        bits += ["Auto-refreshed daily", f"Data last changed {updated}"]
    st.markdown(
        ui.page_header(
            "National overview",
            "Federal Reserve (FRED) macro indicators and Treasury yields, with a composite recession-risk signal.",
            " · ".join(bits),
        ),
        unsafe_allow_html=True,
    )


def status_for_score(score: int, recession_watch: bool) -> tuple[str, str]:
    """(status key for ui.signal_banner, tag text)."""
    if recession_watch:
        return "watch", "Recession watch"
    if score >= 3:
        return "elevated", "Elevated risk"
    return "clear", "No recession watch"


def signal_banner(df: pd.DataFrame) -> None:
    row = latest_complete_row(df)
    score = int(row.get("signal_score", 0))
    recession_watch = bool(row.get("recession_watch", False))
    status, label = status_for_score(score, recession_watch)
    as_of = row["date"].strftime("%b %Y") if pd.notna(row["date"]) else ""
    active = [FLAG_DESCRIPTIONS[f] for f in FLAG_DESCRIPTIONS if bool(row.get(f, False))]
    st.markdown(ui.signal_banner(score, status, label, as_of, active, SIGNAL_NOTE), unsafe_allow_html=True)


def briefing_section(df: pd.DataFrame) -> None:
    # always fed the full history: superlatives ("lowest since 2009") are
    # meaningless when the comparison window is whatever range the sidebar
    # happens to be filtered to
    b = build_briefing(df)
    if b is None:
        return
    st.markdown(ui.section("This month in brief"), unsafe_allow_html=True)
    items = [(item.text, item.tone) for item in [b.score_item] + b.items]
    st.markdown(ui.briefing(b.latest_label, b.previous_label, items, b.quiet), unsafe_allow_html=True)


def kpi_tile(df: pd.DataFrame, key: str) -> ui.Tile:
    meta = INDICATOR_META[key]
    available = df.dropna(subset=[key])
    if available.empty:
        return ui.Tile(label=meta["label"], value="N/A")
    r = available.iloc[-1]
    change, delta = None, None
    mom = r.get(f"{key}_mom_pct")
    if pd.notna(mom):
        delta = round(float(mom), 2)
        change = f"{mom:+.2f}% MoM"
    elif f"{key}_mom_pct" not in df.columns and len(available) > 1:
        # the yield spread is already a gap between two rates, so a percent
        # change of it is meaningless; show the change in points instead
        points = float(r[key] - available[key].iloc[-2])
        delta = round(points, 2)
        change = f"{points:+.2f}pt MoM"
    return ui.Tile(
        label=meta["label"],
        value=meta["fmt"].format(r[key]),
        change=change,
        delta=delta,
        tone=theme.change_tone(theme.GOOD_DIRECTION[key], delta),
        caption=f"as of {r['date']:%b %Y}",
        spark=ui.sparkline_svg(available[key].tail(24).tolist(), meta["slot"]),
    )


def kpi_grid(df: pd.DataFrame, selected: list[str]) -> None:
    st.markdown(ui.section("Latest readings"), unsafe_allow_html=True)
    st.markdown(ui.tile_grid([kpi_tile(df, key) for key in selected], columns=KPI_TILES_PER_ROW),
                unsafe_allow_html=True)


def trends(df: pd.DataFrame, selected: list[str]) -> None:
    t = theme.tokens()
    palette = theme.series_palette()
    st.markdown(ui.section("Indicator trends"), unsafe_allow_html=True)
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
            color = palette[meta["slot"]]
            s = df[["date", key]].dropna()
            fig.add_trace(
                go.Scatter(
                    x=s["date"], y=s[key], mode="lines", name=meta["label"],
                    line=dict(color=color, width=2),
                    fill="tozeroy", fillcolor=rgba(color, 0.06),
                    hovertemplate=f"%{{x|%b %Y}} &nbsp; %{{y:,.1f}} {meta['unit']}<extra></extra>",
                ),
                row=r, col=c,
            )
        fig.update_layout(
            height=210 * rows_n + 30,
            showlegend=False,
            font=dict(family=FONT, color=t["INK_2"], size=12),
            margin=dict(l=0, r=8, t=30, b=0),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            hoverlabel=dict(bgcolor=t["SURFACE"], bordercolor=t["BORDER"], font=dict(family=FONT, color=t["INK"])),
        )
        fig.update_xaxes(showgrid=False, showline=True, linecolor=t["BORDER"], tickfont=dict(color=t["INK_2"], size=11))
        fig.update_yaxes(showgrid=True, gridcolor=t["BORDER"], zeroline=False, tickfont=dict(color=t["INK_2"], size=11))
        for ann in fig.layout.annotations:  # subplot titles
            ann.font.update(size=13, color=t["HEADING"])
            ann.update(x=ann.x, xanchor="center")
        st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)

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
                line=dict(color=palette[meta["slot"]], width=2),
                hovertemplate=f"{meta['label']}: %{{y:+.2f}}%<extra></extra>",
            ))
        fig.add_hline(y=0, line_color=t["INK_2"], line_width=1)
        fig = plotly_layout(fig, height=430)
        st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)


def signal_history(df: pd.DataFrame) -> None:
    t = theme.tokens()
    st.markdown(ui.section("Signal history"), unsafe_allow_html=True)

    fig = go.Figure(go.Scatter(
        x=df["date"], y=df["signal_score"], mode="lines",
        line=dict(color=t["HEADING"], width=2, shape="hv"),
        fill="tozeroy", fillcolor=rgba(t["HEADING"], 0.10),
        hovertemplate="Signal score: %{y} of 7<extra></extra>",
    ))
    fig.add_hline(y=4, line_dash="dot", line_color=t["BAD"], line_width=1.5,
                  annotation_text="Recession-watch threshold",
                  annotation_position="top left",
                  annotation_font=dict(color=t["BAD"], size=11))
    fig = plotly_layout(fig, height=230)
    fig.update_yaxes(range=[0, 7.3], dtick=1)
    st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)

    flag_cols = list(FLAG_DESCRIPTIONS.keys())
    heat = df[["date"] + flag_cols].copy()
    heat[flag_cols] = heat[flag_cols].astype(int)
    heat = heat.set_index("date")[flag_cols]
    z = heat.T.values

    fig2 = go.Figure(go.Heatmap(
        z=z, x=heat.index, y=[FLAG_DESCRIPTIONS[c] for c in flag_cols],
        xgap=0, ygap=5, showscale=False,
        colorscale=[[0, t["BORDER"]], [1, t["BAD"]]],
        zmin=0, zmax=1,
        hovertemplate="%{y}<br>%{x|%b %Y}: %{customdata}<extra></extra>",
        customdata=[["Active" if v else "Inactive" for v in row] for row in z],
    ))
    fig2.update_layout(
        height=250, font=dict(family=FONT, color=t["INK_2"], size=12),
        margin=dict(l=0, r=8, t=6, b=0),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(bgcolor=t["SURFACE"], bordercolor=t["BORDER"], font=dict(family=FONT, color=t["INK"])),
    )
    fig2.update_xaxes(showgrid=False, showline=False, tickfont=dict(color=t["INK_2"]))
    fig2.update_yaxes(showgrid=False, showline=False, tickfont=dict(color=t["INK_2"], size=11), autorange="reversed")
    st.plotly_chart(fig2, width="stretch", config=PLOTLY_CONFIG)


def glossary_section() -> None:
    with st.expander("Glossary: what each indicator means, and what's historically good vs. bad"):
        entries = [
            (INDICATOR_META[key]["slot"], INDICATOR_META[key]["label"], entry["what"], entry["context"])
            for key, entry in GLOSSARY.items()
        ]
        st.markdown(ui.glossary(entries), unsafe_allow_html=True)


def footer() -> None:
    st.markdown(ui.footer(FOOTER_SOURCE, FOOTER_PIPELINE), unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Sidebar + main
# --------------------------------------------------------------------------- #
# quick ranges are anchored to the newest date in the data, not today --
# FRED series trail the calendar by weeks, so "last 6 months" should mean
# the 6 months ending at the last observation.
RANGE_PRESETS = {"6M": 6, "1Y": 12, "2Y": 24, "5Y": 60, "10Y": 120, "All": None}


def sidebar(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    st.sidebar.markdown(ui.sidebar_label("Filters"), unsafe_allow_html=True)

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
    # pills with short names instead of a multiselect: the tag box stacked
    # seven full-length labels and clipped the longest ones
    selected = st.sidebar.pills(
        "Indicators",
        options=list(INDICATOR_META.keys()),
        default=list(INDICATOR_META.keys()),
        selection_mode="multi",
        format_func=lambda k: INDICATOR_META[k]["short"],
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
    states_view.render(load_data(), source_line("FRED, St. Louis Fed", load_metadata()))
    footer()


def revisions_page() -> None:
    revisions_view.render(source_line("ALFRED, St. Louis Fed", load_metadata()))
    footer()


def main() -> None:
    apply_theme()
    nav = st.navigation([
        st.Page(national_page, title="National overview", url_path="national", default=True),
        st.Page(states_page, title="State by state", url_path="states"),
        st.Page(revisions_page, title="Data revisions", url_path="revisions"),
    ])
    nav.run()


if __name__ == "__main__":
    main()
