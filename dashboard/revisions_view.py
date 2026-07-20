"""
Data-revisions page: what did we know, and when did we know it?

Economic data is not fixed history -- first prints get revised for years,
and the revisions are sometimes bigger than the story. Two views built on
ALFRED vintage data (every value each series ever published):

1. GDP growth as first reported vs as we know it now, computed within
   vintages (each growth rate uses only values published at that moment,
   so benchmark rebasings of the GDP *level* can't contaminate it).
2. A time machine: pick a moment, see a series exactly as it looked then
   against what we now know was actually happening.
"""

import io
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from theme import (
    GRIDLINE,
    INK_MUTED,
    INK_PRIMARY,
    STATUS,
    SURFACE,
    base_layout,
    rgba,
)

REPO_ROOT = Path(__file__).parent.parent
VINTAGE_SNAPSHOT = REPO_ROOT / "data" / "vintage_dashboard.parquet"
S3_KEY = "processed/fred_vintages/part-0.parquet"

FIRST_PRINT = "#1b4f96"   # first-release markers
LATEST = "#c98500"        # latest-revision bars
THEN_LINE = "#2a78d6"     # time-machine "known then"
NOW_LINE = INK_MUTED      # time-machine "known now"

# ALFRED's vintage archive only reaches back to late 1991. For older
# observations the earliest archived value is just some early-90s vintage,
# not the number originally published, so a row only counts as having a
# genuine "first print" when its first archived release lands within a
# normal publication lag of the observation period itself.
MAX_FIRST_PRINT_LAG_DAYS = 200

TIME_MACHINE_SERIES = {
    "Unemployment rate": {"label": "unemployment_rate", "fmt": "{:.1f}%", "mode": "level",
                          "unit": ""},
    "Housing starts": {"label": "housing_starts", "fmt": "{:,.0f}K", "mode": "level",
                       "unit": "thousands of units, annualized"},
    "Nonfarm payrolls, monthly change": {"label": "nonfarm_payrolls", "fmt": "{:+,.0f}K",
                                         "mode": "diff", "unit": "thousands of jobs"},
}

MOMENTS = {
    "Dot-com bust (Mar 2001)": pd.Timestamp("2001-03-15"),
    "Financial crisis (Sep 2008)": pd.Timestamp("2008-09-15"),
    "Covid (Apr 2020)": pd.Timestamp("2020-04-15"),
    "Custom date": None,
}

# NBER recessions inside the vintage-archive era, for chart shading
NBER_RECESSIONS = [
    ("1990-07-01", "1991-03-01"),
    ("2001-03-01", "2001-11-01"),
    ("2007-12-01", "2009-06-01"),
    ("2020-02-01", "2020-04-01"),
]


def add_recession_bands(fig: go.Figure, x_min: pd.Timestamp, x_max: pd.Timestamp) -> None:
    for s, e in NBER_RECESSIONS:
        s, e = pd.Timestamp(s), pd.Timestamp(e)
        if e < x_min or s > x_max:
            continue
        fig.add_vrect(x0=max(s, x_min), x1=min(e, x_max),
                      fillcolor=rgba(INK_MUTED, 0.10), line_width=0, layer="below")


@st.cache_data(ttl=3600, show_spinner="Loading vintage data...")
def load_vintages() -> pd.DataFrame | None:
    if VINTAGE_SNAPSHOT.exists():
        df = pd.read_parquet(VINTAGE_SNAPSHOT)
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
    df["release_date"] = pd.to_datetime(df["release_date"])
    return df.sort_values(["label", "date", "release_date"]).reset_index(drop=True)


@st.cache_data(ttl=3600)
def first_vs_latest(label: str, mode: str) -> pd.DataFrame:
    """Per observation: the change vs the previous period as first printed
    vs as currently estimated. mode "pct" gives % change (GDP growth),
    "diff" gives the absolute change (payroll gains).

    Each first-print change compares the first-released value against the
    previous period's value *as it stood on that same release date*, so
    both sides come from one vintage and level rebasings cancel out.
    """
    v = load_vintages()
    g = v[v["label"] == label].sort_values(["date", "release_date"])
    dates = sorted(g["date"].unique())
    by_date = {d: sub for d, sub in g.groupby("date")}

    rows = []
    for i, d in enumerate(dates):
        if i == 0:
            continue
        sub = by_date[d]
        first_release = sub["release_date"].iloc[0]
        first_value = sub["value"].iloc[0]
        latest_value = sub["value"].iloc[-1]

        prev = by_date[dates[i - 1]]
        prev_asof = prev[prev["release_date"] <= first_release]
        if prev_asof.empty or (first_release - d).days > MAX_FIRST_PRINT_LAG_DAYS:
            continue
        prev_first = prev_asof["value"].iloc[-1]
        prev_latest = prev["value"].iloc[-1]

        if mode == "pct":
            first = (first_value / prev_first - 1) * 100
            latest = (latest_value / prev_latest - 1) * 100
        else:
            first = first_value - prev_first
            latest = latest_value - prev_latest
        rows.append({
            "date": d,
            "first_release": first_release,
            "first_growth": first,
            "latest_growth": latest,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["revision_pp"] = df["latest_growth"] - df["first_growth"]
    df["sign_flip"] = (df["first_growth"] * df["latest_growth"]) < 0
    return df


def gdp_growth_revisions() -> pd.DataFrame:
    return first_vs_latest("gdp", "pct")


def _quarter(ts: pd.Timestamp) -> str:
    return f"Q{(ts.month - 1) // 3 + 1} {ts.year}"


def as_of_series(v: pd.DataFrame, label: str, cutoff: pd.Timestamp) -> pd.Series:
    """The series exactly as it was published on `cutoff`."""
    s = v[(v["label"] == label) & (v["release_date"] <= cutoff) & (v["date"] <= cutoff)]
    s = s.sort_values(["date", "release_date"])
    return s.groupby("date")["value"].last()


def latest_series(v: pd.DataFrame, label: str, cutoff: pd.Timestamp) -> pd.Series:
    """The same period as we understand it today."""
    s = v[(v["label"] == label) & (v["date"] <= cutoff)].sort_values(["date", "release_date"])
    return s.groupby("date")["value"].last()


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #
def stat_tiles(rev: pd.DataFrame) -> None:
    flips = int(rev["sign_flip"].sum())
    total = len(rev)
    worst = rev.loc[rev["revision_pp"].abs().idxmax()]
    avg_abs = rev["revision_pp"].abs().mean()

    c1, c2, c3 = st.columns(3, gap="medium")
    with c1.container(border=True):
        st.metric("Quarters whose growth later flipped sign", f"{flips} of {total}")
        st.markdown('<div class="tile-asof">reported growth when the economy was shrinking, or vice versa</div>',
                    unsafe_allow_html=True)
    with c2.container(border=True):
        st.metric("Largest single revision", f"{worst['revision_pp']:+.1f}pp",
                  delta=_quarter(worst["date"]), delta_color="off")
        st.markdown('<div class="tile-asof">difference between the first print and today\'s estimate</div>',
                    unsafe_allow_html=True)
    with c3.container(border=True):
        st.metric("Average revision size", f"{avg_abs:.2f}pp")
        st.markdown('<div class="tile-asof">mean absolute change in quarterly growth since first print</div>',
                    unsafe_allow_html=True)


def _revision_chart(rev: pd.DataFrame, labeler, value_hover: str, key: str,
                    y_range: tuple[float, float] | None = None) -> None:
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=rev["date"], y=rev["latest_growth"], name="Today's estimate",
        marker_color=rgba(LATEST, 0.55), marker_line_width=0,
        customdata=[labeler(d) for d in rev["date"]],
        hovertemplate="%{customdata}<br>Today: " + value_hover + "<extra></extra>",
    ))
    flip = rev[rev["sign_flip"]]
    normal = rev[~rev["sign_flip"]]
    fig.add_trace(go.Scatter(
        x=normal["date"], y=normal["first_growth"], name="First print", mode="markers",
        marker=dict(color=FIRST_PRINT, size=5),
        customdata=[labeler(d) for d in normal["date"]],
        hovertemplate="%{customdata}<br>First print: " + value_hover + "<extra></extra>",
    ))
    if not flip.empty:
        fig.add_trace(go.Scatter(
            x=flip["date"], y=flip["first_growth"], name="First print (sign later flipped)",
            mode="markers",
            marker=dict(color=FIRST_PRINT, size=7,
                        line=dict(color=STATUS["critical"], width=2)),
            customdata=[labeler(d) for d in flip["date"]],
            hovertemplate="%{customdata}<br>First print: " + value_hover + " (sign later flipped)<extra></extra>",
        ))
    add_recession_bands(fig, rev["date"].min(), rev["date"].max())
    fig.add_hline(y=0, line_color=INK_MUTED, line_width=1)
    fig = base_layout(fig, height=380)
    fig.update_layout(bargap=0.35)
    if y_range is not None:
        fig.update_yaxes(range=list(y_range))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=key)


def first_print_section(rev_gdp: pd.DataFrame) -> None:
    st.markdown('<div class="section-label">As first reported vs today</div>', unsafe_allow_html=True)
    tab_gdp, tab_pay = st.tabs(["GDP growth", "Payroll gains"])

    with tab_gdp:
        st.caption(
            "Nominal GDP, quarter-over-quarter percent change. Bars are today's estimate; dots are what was "
            "first reported at the time. Red-ringed dots mark quarters where revisions later flipped the sign "
            "of growth; shaded bands are NBER recessions. Each first print is compared within its own data "
            "vintage, so statistical re-basings of the GDP level don't distort it."
        )
        _revision_chart(rev_gdp, _quarter, "%{y:+.1f}%", key="rev_gdp")

    with tab_pay:
        rev_pay = first_vs_latest("nonfarm_payrolls", "diff")
        if rev_pay.empty:
            st.info("No payroll vintage data available yet.")
            return
        avg_miss = rev_pay["revision_pp"].abs().mean()
        flips = int(rev_pay["sign_flip"].sum())
        st.caption(
            f"Monthly change in nonfarm payrolls, in thousands of jobs: the headline number of every "
            f"jobs report. Across {len(rev_pay)} months with a true first print, revisions moved the "
            f"number by {avg_miss:,.0f}K jobs on average, and {flips} months that reported job gains "
            f"turned out to be losses (or the reverse). Showing the last 12 years; the Covid collapse "
            f"and rebound (about 20 million jobs each way in spring 2020) run far past the visible "
            f"range, which is clipped so ordinary months stay readable."
        )
        window = rev_pay[rev_pay["date"] >= rev_pay["date"].max() - pd.DateOffset(years=12)]
        # y-range from the typical spread, not the Covid outlier
        bound = float(window[["first_growth", "latest_growth"]].abs().quantile(0.98).max()) * 1.35
        _revision_chart(window, lambda d: f"{pd.Timestamp(d):%b %Y}", "%{y:+,.0f}K", key="rev_pay",
                        y_range=(-bound, bound))


def time_machine(v: pd.DataFrame) -> None:
    st.markdown('<div class="section-label">Time machine</div>', unsafe_allow_html=True)
    st.caption(
        "Pick a moment and a series: the solid line is the data exactly as anyone could have seen it on "
        "that day; the dotted line is what we now know was actually happening. The gap between them is "
        "why real-time policy is hard."
    )

    left, right = st.columns([1.2, 1], gap="medium")
    with left:
        moment = st.segmented_control(
            "Moment", options=list(MOMENTS), default="Financial crisis (Sep 2008)",
            key="tm_moment", label_visibility="collapsed",
        )
    with right:
        series_name = st.selectbox("Series", list(TIME_MACHINE_SERIES), key="tm_series",
                                   label_visibility="collapsed")

    if moment == "Custom date" or not moment:
        max_d = v["release_date"].max().to_pydatetime()
        cutoff = pd.Timestamp(st.slider(
            "As-of date",
            min_value=pd.Timestamp("1995-01-01").to_pydatetime(),
            max_value=max_d,
            value=pd.Timestamp("2008-09-15").to_pydatetime(),
            format="MMM YYYY",
            key="tm_slider",
        ))
    else:
        cutoff = MOMENTS[moment]

    spec = TIME_MACHINE_SERIES[series_name]
    then = as_of_series(v, spec["label"], cutoff)
    now = latest_series(v, spec["label"], cutoff)
    if spec["mode"] == "diff":
        then, now = then.diff(), now.diff()

    window_start = cutoff - pd.DateOffset(years=4)
    then = then[then.index >= window_start]
    now = now[now.index >= window_start]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=then.index, y=then.values, name=f"As known on {cutoff:%b %d, %Y}",
        line=dict(color=THEN_LINE, width=2.2),
        hovertemplate="Known then: %{y:,.1f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=now.index, y=now.values, name="As we know it now",
        line=dict(color=NOW_LINE, width=2, dash="dot"),
        hovertemplate="Known now: %{y:,.1f}<extra></extra>",
    ))
    add_recession_bands(fig, window_start, cutoff)
    fig = base_layout(fig, height=360)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    # the biggest then-vs-now gaps inside the window, as a small table
    joined = pd.DataFrame({"then": then, "now": now}).dropna()
    if not joined.empty:
        joined["gap"] = joined["now"] - joined["then"]
        top = joined.reindex(joined["gap"].abs().sort_values(ascending=False).index).head(5)
        unit_bit = f" ({spec['unit']})" if spec["unit"] else ""
        st.caption(f"The biggest gaps between what was known then and now, in this window{unit_bit}:")
        display = pd.DataFrame({
            "Month": [f"{d:%b %Y}" for d in top.index],
            "Reported at the time": [spec["fmt"].format(v) for v in top["then"]],
            "Known now": [spec["fmt"].format(v) for v in top["now"]],
            "Gap": [f"{v:+,.1f}" for v in top["gap"]],
        })
        st.dataframe(display, width="stretch", hide_index=True)


def explainer() -> None:
    with st.expander("Why do the numbers change?"):
        st.markdown(
            """
            Statistical agencies publish early to be timely, then revise as fuller source data
            arrives: late survey responses, tax records, annual benchmarks against near-complete
            censuses, and updated seasonal adjustment. GDP's advance estimate is built on
            projections for many components; payrolls' first print comes from a survey subset.

            The practical consequence: **the economy you read about in real time is a draft.**
            Several recessions were not visible in the first prints of the data: early 2008
            GDP releases showed a growing economy. This page exists to make that draft-ness
            visible instead of pretending the latest numbers were always known.

            Vintage data comes from [ALFRED](https://alfred.stlouisfed.org/), the St. Louis
            Fed's archival companion to FRED.
            """
        )


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #
def render() -> None:
    v = load_vintages()
    if v is None or v.empty:
        st.info(
            "Vintage data hasn't been generated yet. Run the pipeline "
            "(ingestion/fetch_fred_vintages.py, spark/transform_vintages_local.py, "
            "dbt, scripts/export_dashboard_snapshot.py) or wait for the daily refresh."
        )
        return

    st.markdown(
        """
        <div class="hero-title">Data revisions</div>
        <div class="hero-sub">Economic data is a draft: first prints get revised for years.
        Every number here as it was originally published, against what it became.</div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")

    rev = gdp_growth_revisions()
    if not rev.empty:
        stat_tiles(rev)
        st.divider()
        first_print_section(rev)
        st.divider()
    time_machine(v)
    st.write("")
    explainer()
