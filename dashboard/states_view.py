"""
State-by-state page: how is one state doing vs the country and vs the other
49 (+DC)? Unemployment (monthly), FHFA house-price growth (quarterly), and
per-capita income (annual), each with the state's rank in the field as of
its latest reading, plus a national choropleth per metric.

Rendered by app.py through st.navigation; reads the committed snapshot the
daily refresh produces (data/state_dashboard.parquet).
"""

import io
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from theme import (
    DIV_AMBER_BLUE,
    GRIDLINE,
    INK_MUTED,
    INK_PRIMARY,
    SEQ_BLUE,
    SEQ_GREEN,
    SURFACE,
    base_layout,
    rgba,
)

REPO_ROOT = Path(__file__).parent.parent
STATE_SNAPSHOT = REPO_ROOT / "data" / "state_dashboard.parquet"
S3_KEY = "processed/state_indicators/part-0.parquet"

STATE_LINE = "#2a78d6"   # selected state's series colour, fixed
NATIONAL_LINE = INK_MUTED  # U.S. reference line, always the muted ink
HPI_LINE = "#4a3aa7"

RANGE_PRESETS = {"5Y": 60, "10Y": 120, "20Y": 240, "All": None}

METRICS = {
    "Unemployment rate": {
        "col": "unemployment_rate",
        "rank_col": "unemployment_rank",
        "fmt": "{:.1f}%",
        "colorscale": SEQ_BLUE,
        "diverging": False,
        "rank_word": "lowest",
    },
    "House-price growth (YoY)": {
        "col": "house_price_index_yoy_pct",
        "rank_col": "hpi_growth_rank",
        "fmt": "{:+.1f}%",
        "colorscale": DIV_AMBER_BLUE,
        "diverging": True,
        "rank_word": "fastest-growing",
    },
    "Per-capita income": {
        "col": "per_capita_income",
        "rank_col": "income_rank",
        "fmt": "${:,.0f}",
        "colorscale": SEQ_GREEN,
        "diverging": False,
        "rank_word": "highest",
    },
}


@st.cache_data(ttl=3600, show_spinner="Loading state data...")
def load_state_data() -> pd.DataFrame | None:
    if STATE_SNAPSHOT.exists():
        df = pd.read_parquet(STATE_SNAPSHOT)
    else:
        bucket = os.environ.get("AWS_BUCKET_NAME")
        if not bucket:
            return None
        import boto3

        s3 = boto3.client(
            "s3",
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
        obj = s3.get_object(Bucket=bucket, Key=S3_KEY)
        df = pd.read_parquet(io.BytesIO(obj["Body"].read()))
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["state", "date"]).reset_index(drop=True)


def _ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def _quarter(ts: pd.Timestamp) -> str:
    return f"Q{(ts.month - 1) // 3 + 1} {ts.year}"


def _rank_phrase(rank, total: int, word: str) -> str | None:
    if rank is None or pd.isna(rank):
        return None
    rank = int(rank)
    if rank == 1:
        return f"{word} of {total}"
    return f"{_ordinal(rank)} {word} of {total}"


def latest_by_state(df: pd.DataFrame, col: str, rank_col: str) -> pd.DataFrame:
    cols = ["date", "state", "state_name", col]
    if rank_col in df.columns:
        cols.append(rank_col)
    d = df.dropna(subset=[col])
    # df is sorted by (state, date), so the tail row per state is its latest
    return d.groupby("state").tail(1)[cols].reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #
def _tile(label: str, value: str, asof: str, rank_phrase: str | None, delta: str | None = None,
          delta_inverse: bool = False) -> None:
    st.metric(
        label=label,
        value=value,
        delta=delta,
        delta_color=("inverse" if delta_inverse else "normal") if delta else "off",
    )
    bits = [f"as of {asof}"]
    if rank_phrase:
        bits.append(rank_phrase)
    st.markdown(f'<div class="tile-asof">{" &nbsp;·&nbsp; ".join(bits)}</div>', unsafe_allow_html=True)


def kpi_row(sdf: pd.DataFrame, total_states: int) -> None:
    st.markdown('<div class="section-label">Latest readings</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3, gap="medium")

    ur = sdf.dropna(subset=["unemployment_rate"])
    with c1.container(border=True):
        if ur.empty:
            st.metric("Unemployment rate", "N/A")
        else:
            r = ur.iloc[-1]
            yoy = r.get("unemployment_rate_yoy")
            _tile(
                "Unemployment rate",
                f"{r['unemployment_rate']:.1f}%",
                r["date"].strftime("%b %Y"),
                _rank_phrase(r.get("unemployment_rank"), total_states, "lowest"),
                delta=f"{yoy:+.1f}pp YoY" if pd.notna(yoy) else None,
                delta_inverse=True,
            )

    hpi = sdf.dropna(subset=["house_price_index_yoy_pct"])
    with c2.container(border=True):
        if hpi.empty:
            st.metric("House-price growth", "N/A")
        else:
            r = hpi.iloc[-1]
            _tile(
                "House-price growth",
                f"{r['house_price_index_yoy_pct']:+.1f}% YoY",
                _quarter(r["date"]),
                _rank_phrase(r.get("hpi_growth_rank"), total_states, "fastest-growing"),
            )

    inc = sdf.dropna(subset=["per_capita_income"])
    with c3.container(border=True):
        if inc.empty:
            st.metric("Per-capita income", "N/A")
        else:
            r = inc.iloc[-1]
            yoy = r.get("per_capita_income_yoy_pct")
            _tile(
                "Per-capita income",
                f"${r['per_capita_income']:,.0f}",
                r["date"].strftime("%Y"),
                _rank_phrase(r.get("income_rank"), total_states, "highest"),
                delta=f"{yoy:+.1f}% YoY" if pd.notna(yoy) else None,
            )


def trend_charts(sdf: pd.DataFrame, national: pd.DataFrame, state_name: str, months: int | None) -> None:
    st.markdown('<div class="section-label">Trends vs the nation</div>', unsafe_allow_html=True)

    if months is not None:
        cutoff = sdf["date"].max() - pd.DateOffset(months=months)
        sdf = sdf[sdf["date"] >= cutoff]
        national = national[national["date"] >= cutoff]

    left, right = st.columns(2, gap="medium")

    with left:
        st.caption(f"Unemployment rate: {state_name} vs U.S.")
        s = sdf.dropna(subset=["unemployment_rate"])
        n = national.dropna(subset=["unemployment_rate"])
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=s["date"], y=s["unemployment_rate"], name=state_name,
            line=dict(color=STATE_LINE, width=2),
            hovertemplate=f"{state_name}: %{{y:.1f}}%<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=n["date"], y=n["unemployment_rate"], name="U.S.",
            line=dict(color=NATIONAL_LINE, width=2, dash="dot"),
            hovertemplate="U.S.: %{y:.1f}%<extra></extra>",
        ))
        fig = base_layout(fig, height=310)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    with right:
        st.caption(f"House-price growth, year-over-year: {state_name}")
        h = sdf.dropna(subset=["house_price_index_yoy_pct"])
        fig = go.Figure(go.Scatter(
            x=h["date"], y=h["house_price_index_yoy_pct"], name="HPI YoY",
            line=dict(color=HPI_LINE, width=2),
            fill="tozeroy", fillcolor=rgba(HPI_LINE, 0.07),
            hovertemplate="%{y:+.1f}% YoY<extra></extra>",
        ))
        fig.add_hline(y=0, line_color=INK_MUTED, line_width=1)
        fig = base_layout(fig, height=310)
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def choropleth(df: pd.DataFrame, total_states: int) -> None:
    st.markdown('<div class="section-label">The whole map</div>', unsafe_allow_html=True)
    choice = st.segmented_control(
        "Map metric", options=list(METRICS), default=list(METRICS)[0],
        key="state_map_metric", label_visibility="collapsed",
    )
    if not choice:
        choice = list(METRICS)[0]
    spec = METRICS[choice]

    latest = latest_by_state(df, spec["col"], spec["rank_col"])
    if latest.empty:
        st.info("No data available for this metric yet.")
        return
    asof = latest["date"].max()
    asof_str = _quarter(asof) if spec["col"].startswith("house") else (
        asof.strftime("%Y") if spec["col"] == "per_capita_income" else asof.strftime("%b %Y")
    )

    def hover(row) -> str:
        val = spec["fmt"].format(row[spec["col"]])
        phrase = _rank_phrase(row.get(spec["rank_col"]), total_states, spec["rank_word"])
        return f"<b>{row['state_name']}</b><br>{val}" + (f"<br>{phrase}" if phrase else "")

    z = latest[spec["col"]]
    kwargs = {}
    if spec["diverging"]:
        bound = max(abs(z.min()), abs(z.max()))
        kwargs = dict(zmin=-bound, zmax=bound)

    fig = go.Figure(go.Choropleth(
        locations=latest["state"],
        locationmode="USA-states",
        z=z,
        colorscale=spec["colorscale"],
        marker_line_color=SURFACE,
        marker_line_width=1,
        text=[hover(r) for _, r in latest.iterrows()],
        hovertemplate="%{text}<extra></extra>",
        colorbar=dict(
            thickness=10, len=0.7, outlinewidth=0,
            tickfont=dict(color=INK_MUTED, size=11),
        ),
        **kwargs,
    ))
    fig.update_geos(
        scope="usa",
        bgcolor="rgba(0,0,0,0)",
        showlakes=False,
        landcolor=GRIDLINE,
        subunitcolor=SURFACE,
    )
    # plotly.js recomputes the USA-map projection scale on every resize or
    # responsive-autosize pass, and gets it wrong -- the map collapses to a
    # postage stamp. Streamlit's plotly component always autosizes, so the map
    # goes through a plain iframe instead, at a fixed pixel size that fits the
    # iframe (no overflow, no resize) with the responsive handler disabled:
    # the initial render is the only one that ever happens, and it's correct.
    fig.update_layout(
        width=880,
        height=470,
        margin=dict(l=0, r=0, t=8, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=GRIDLINE, font=dict(color=INK_PRIMARY)),
    )
    import streamlit.components.v1 as components

    html = fig.to_html(
        include_plotlyjs="cdn",
        full_html=True,
        config={"displayModeBar": False, "responsive": False},
    )
    # the iframe's first paint can happen before it has its final size, which
    # leaves the geo paths drawn at the wrong scale even though plotly's
    # internal projection state is correct; one deferred redraw repaints from
    # that (correct) state
    html = html.replace(
        "</body>",
        "<script>window.addEventListener('load',function(){setTimeout(function(){"
        "var gd=document.querySelector('.js-plotly-plot');"
        "if(gd&&window.Plotly){Plotly.redraw(gd);}},400);});</script></body>",
    )
    components.html(html, height=490)
    st.caption(f"{choice}, latest reading per state (as of {asof_str}).")


def rankings_table(df: pd.DataFrame) -> None:
    with st.expander("All states, ranked (latest readings)"):
        ur = latest_by_state(df, "unemployment_rate", "unemployment_rank")
        hpi = latest_by_state(df, "house_price_index_yoy_pct", "hpi_growth_rank")
        inc = latest_by_state(df, "per_capita_income", "income_rank")
        merged = (
            ur[["state", "state_name", "unemployment_rate"]]
            .merge(hpi[["state", "house_price_index_yoy_pct"]], on="state", how="outer")
            .merge(inc[["state", "per_capita_income"]], on="state", how="outer")
            .sort_values("unemployment_rate")
            .reset_index(drop=True)
        )
        st.dataframe(
            merged,
            width="stretch",
            hide_index=True,
            column_config={
                "state": st.column_config.TextColumn("Code", width="small"),
                "state_name": st.column_config.TextColumn("State"),
                "unemployment_rate": st.column_config.NumberColumn("Unemployment", format="%.1f%%"),
                "house_price_index_yoy_pct": st.column_config.NumberColumn("House-price growth YoY", format="%+.1f%%"),
                "per_capita_income": st.column_config.NumberColumn("Per-capita income", format="$%,.0f"),
            },
        )


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #
def render(national: pd.DataFrame) -> None:
    df = load_state_data()
    if df is None or df.empty:
        st.info(
            "State-level data hasn't been generated yet. Run the pipeline "
            "(ingestion/fetch_fred_states.py, spark/transform_states_local.py, "
            "dbt, scripts/export_dashboard_snapshot.py) or wait for the daily refresh."
        )
        return

    total_states = df["state"].nunique()
    names = df[["state", "state_name"]].drop_duplicates().sort_values("state_name")

    st.sidebar.markdown('<div class="section-label">Filters</div>', unsafe_allow_html=True)
    state_name = st.sidebar.selectbox("State", names["state_name"].tolist(),
                                      index=names["state_name"].tolist().index("California"))
    range_choice = st.sidebar.segmented_control(
        "Date range", options=list(RANGE_PRESETS), default="20Y", key="state_range",
    )
    months = RANGE_PRESETS.get(range_choice or "All")

    st.markdown(
        f"""
        <div class="hero-title">State by state</div>
        <div class="hero-sub">Unemployment, house prices, and income for all 50 states + DC,
        with each state ranked against the field.</div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")

    sdf = df[df["state_name"] == state_name]
    kpi_row(sdf, total_states)
    st.divider()
    trend_charts(sdf, national, state_name, months)
    st.divider()
    choropleth(df, total_states)
    rankings_table(df)
