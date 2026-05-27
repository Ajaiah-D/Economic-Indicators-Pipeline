import io
import os
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Economic Indicators Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

LOCAL_PARQUET = Path(__file__).parent.parent / "dbt" / "target" / "economic_dashboard.parquet"
S3_PARQUET_KEY = "processed/economic_indicators"

INDICATOR_META = {
    "cpi":                {"label": "CPI",                "unit": "Index (1982-84=100)", "color": "#e74c3c"},
    "unemployment_rate":  {"label": "Unemployment Rate",  "unit": "%",                  "color": "#e67e22"},
    "gdp":                {"label": "GDP",                "unit": "Billions USD",        "color": "#2ecc71"},
    "fed_funds_rate":     {"label": "Fed Funds Rate",     "unit": "%",                  "color": "#3498db"},
    "housing_starts":     {"label": "Housing Starts",     "unit": "Thousands of Units", "color": "#9b59b6"},
    "consumer_sentiment": {"label": "Consumer Sentiment", "unit": "Index",              "color": "#1abc9c"},
}

FLAG_DESCRIPTIONS = {
    "flag_unemployment_rising": "Unemployment Rising",
    "flag_gdp_contracting":     "GDP Contracting",
    "flag_inflation_elevated":  "Inflation Elevated (>3% annualised)",
    "flag_fed_rate_elevated":   "Fed Rate Elevated (>4%)",
    "flag_housing_declining":   "Housing Starts Declining",
    "flag_sentiment_falling":   "Consumer Sentiment Falling",
}


@st.cache_data(ttl=3600, show_spinner="Loading economic data...")
def load_data() -> pd.DataFrame:
    if LOCAL_PARQUET.exists():
        df = pd.read_parquet(LOCAL_PARQUET)
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


def sidebar(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    st.sidebar.title("Controls")

    min_date = df["date"].min().date()
    max_date = df["date"].max().date()

    start, end = st.sidebar.date_input(
        "Date range",
        value=(max(min_date, date(2015, 1, 1)), max_date),
        min_value=min_date,
        max_value=max_date,
    )

    selected = st.sidebar.multiselect(
        "Indicators to display",
        options=list(INDICATOR_META.keys()),
        default=list(INDICATOR_META.keys()),
        format_func=lambda k: INDICATOR_META[k]["label"],
    )

    mask = (df["date"].dt.date >= start) & (df["date"].dt.date <= end)
    return df[mask].copy(), selected


def kpi_cards(df: pd.DataFrame, selected: list[str]) -> None:
    st.subheader("Latest Readings")
    latest = df.iloc[-1]
    for col, key in zip(st.columns(len(selected)), selected):
        meta = INDICATOR_META[key]
        val = latest.get(key)
        mom = latest.get(f"{key}_mom_pct")
        col.metric(
            label=meta["label"],
            value=f"{val:,.2f}" if pd.notna(val) else "N/A",
            delta=f"{mom:+.2f}% MoM" if pd.notna(mom) else "N/A",
        )


def time_series_chart(df: pd.DataFrame, selected: list[str]) -> None:
    st.subheader("Indicator Trends Over Time")

    tabs = st.tabs(["Raw Values", "Month-over-Month %", "3-Month Rolling Average"])
    variants = [("", ""), ("_mom_pct", " (MoM %)"), ("_3m_avg", " (3-Month Avg)")]

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
                    line=dict(color=meta["color"], width=2),
                    hovertemplate=f"{meta['label']}: %{{y:.2f}} {meta['unit']}<br>%{{x|%b %Y}}<extra></extra>",
                ))
            fig.update_layout(
                height=450,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                margin=dict(l=0, r=0, t=30, b=0),
                hovermode="x unified",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            fig.update_xaxes(showgrid=False)
            fig.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.2)")
            st.plotly_chart(fig, use_container_width=True)


def signal_panel(df: pd.DataFrame) -> None:
    st.subheader("Economic Signals")
    latest = df.iloc[-1]

    active_flags = [FLAG_DESCRIPTIONS[f] for f in FLAG_DESCRIPTIONS if latest.get(f, False)]
    score = int(latest.get("signal_score", 0))
    recession_watch = bool(latest.get("recession_watch", False))

    col_score, col_flags = st.columns([1, 3])

    with col_score:
        colour = "#e74c3c" if recession_watch else "#f39c12" if score >= 2 else "#2ecc71"
        watch_label = f"<div style='margin-top:8px; font-weight:600; color:{colour}'>⚠ RECESSION WATCH</div>" if recession_watch else ""
        st.markdown(
            f"""
            <div style="text-align:center; padding:20px; border-radius:10px;
                        background:{colour}22; border:2px solid {colour}">
                <div style="font-size:3rem; font-weight:bold; color:{colour}">{score}/6</div>
                <div style="font-size:1rem; color:{colour}">Signal Score</div>
                {watch_label}
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_flags:
        if active_flags:
            st.markdown("**Active stress signals:**")
            for flag in active_flags:
                st.markdown(f"- 🔴 {flag}")
        else:
            st.markdown("**No active stress signals — economic conditions appear stable.**")

    fig = px.area(df, x="date", y="signal_score", title="Historical Signal Score (0-6)",
                  color_discrete_sequence=["#e74c3c"])
    fig.add_hline(y=3, line_dash="dot", line_color="orange", annotation_text="Recession Watch threshold")
    fig.update_layout(height=250, margin=dict(l=0, r=0, t=40, b=0),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.update_yaxes(range=[0, 6], dtick=1)
    st.plotly_chart(fig, use_container_width=True)


def flag_heatmap(df: pd.DataFrame) -> None:
    st.subheader("Flag History Heatmap")
    flag_cols = list(FLAG_DESCRIPTIONS.keys())
    heat_df = df[["date"] + flag_cols].copy()
    heat_df[flag_cols] = heat_df[flag_cols].astype(int)
    heat_df = heat_df.set_index("date")[flag_cols]

    fig = px.imshow(
        heat_df.T,
        labels=dict(x="Date", y="Signal", color="Active"),
        y=[FLAG_DESCRIPTIONS[c] for c in flag_cols],
        color_continuous_scale=["#2ecc71", "#e74c3c"],
        aspect="auto",
    )
    fig.update_layout(height=300, margin=dict(l=0, r=0, t=0, b=0), coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)


def main() -> None:
    st.title("📊 U.S. Economic Indicators Dashboard")
    st.caption(
        "Data: Federal Reserve Economic Data (FRED) · "
        "Pipeline: Python → Airflow → PySpark → dbt → Streamlit"
    )

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
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
