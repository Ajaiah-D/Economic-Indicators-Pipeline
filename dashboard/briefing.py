"""
Auto-generated monthly briefing.

Diffs the latest complete month against the one before it, and scans each
series' full history for superlatives -- record levels, unusually large
moves, multi-month streaks -- so the dashboard can say "housing starts fell
for a 5th straight month, the longest slide since 2009" instead of just
showing a number. This is the same computation financial journalists do by
hand for headlines ("sharpest drop since June 2022"), automated over the
full history sitting in the snapshot.

Pure pandas, no Streamlit imports: app.py renders whatever this returns.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# A superlative only gets said out loud if it reaches back far enough to be
# interesting: 2 years for moves/streaks, 5 for outright levels (levels drift,
# so "highest since last spring" is usually just trend, not news).
MIN_GAP_MONTHS_MOVE = 24
MIN_GAP_MONTHS_LEVEL = 60
MIN_STREAK = 3

FLAG_TO_INDICATOR = {
    "flag_unemployment_rising": "unemployment_rate",
    "flag_gdp_contracting": "gdp",
    "flag_inflation_elevated": "cpi",
    "flag_fed_rate_elevated": "fed_funds_rate",
    "flag_housing_declining": "housing_starts",
    "flag_sentiment_falling": "consumer_sentiment",
    "flag_yield_curve_inverted": "yield_spread",
}

# monthly series a month needs before its briefing is meaningful (GDP is
# quarterly and late; the signal page applies the same rule)
MONTHLY_CORE = ["cpi", "unemployment_rate", "housing_starts", "consumer_sentiment"]

QUIET_LABELS = {
    "cpi": "inflation",
    "unemployment_rate": "unemployment",
    "gdp": "GDP",
    "fed_funds_rate": "the fed funds rate",
    "housing_starts": "housing starts",
    "consumer_sentiment": "consumer sentiment",
    "yield_spread": "the yield spread",
}


@dataclass
class BriefingItem:
    text: str  # sentence with <strong> emphasis, rendered as HTML
    tone: str  # "warn" | "good" | "neutral"


@dataclass
class Briefing:
    latest_label: str
    previous_label: str
    items: list[BriefingItem]
    quiet: list[str]  # readable names of indicators with nothing notable
    score_item: BriefingItem


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _month(ts) -> str:
    return pd.Timestamp(ts).strftime("%b %Y")


def _quarter(ts) -> str:
    ts = pd.Timestamp(ts)
    return f"Q{(ts.month - 1) // 3 + 1} {ts.year}"


def _ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def _months_between(a, b) -> int:
    a, b = pd.Timestamp(a), pd.Timestamp(b)
    return (b.year - a.year) * 12 + (b.month - a.month)


def _extreme_note(dates: pd.Series, values: pd.Series, unit_word: str = "level") -> str | None:
    """'highest/lowest <unit_word> since X' if the current value is a long-run
    extreme in either direction; None otherwise. Last element is current."""
    if len(values) < 2:
        return None
    cur_d, cur_v = dates.iloc[-1], values.iloc[-1]
    hist_d, hist_v = dates.iloc[:-1], values.iloc[:-1]
    for kind, mask in (("highest", hist_v >= cur_v), ("lowest", hist_v <= cur_v)):
        prior = hist_d[mask.fillna(True)]  # NaN history can't confirm a record
        if prior.empty:
            return f"the {kind} {unit_word} on record"
        if _months_between(prior.iloc[-1], cur_d) >= MIN_GAP_MONTHS_LEVEL:
            return f"the {kind} {unit_word} since {_month(prior.iloc[-1])}"
    return None


def _move_note(dates: pd.Series, changes: pd.Series, period_word: str = "monthly") -> str | None:
    """'sharpest monthly rise/drop since X' if the newest change is the biggest
    same-direction change in a long time. Last element is current."""
    if len(changes) < 2:
        return None
    cur_d, cur_c = dates.iloc[-1], changes.iloc[-1]
    if pd.isna(cur_c) or cur_c == 0:
        return None
    word = "rise" if cur_c > 0 else "drop"
    mask = changes.iloc[:-1] >= cur_c if cur_c > 0 else changes.iloc[:-1] <= cur_c
    prior = dates.iloc[:-1][mask.fillna(True)]
    if prior.empty:
        return f"the sharpest {period_word} {word} on record"
    if _months_between(prior.iloc[-1], cur_d) >= MIN_GAP_MONTHS_MOVE:
        return f"the sharpest {period_word} {word} since {_month(prior.iloc[-1])}"
    return None


def _streak_note(dates: pd.Series, changes: pd.Series,
                 words: tuple[str, str] = ("monthly rise", "monthly decline")) -> str | None:
    """'its 5th straight monthly decline, the longest slide since X' when the
    series has moved the same direction 3+ periods in a row."""
    signs = np.sign(changes.to_numpy(dtype=float))
    signs = signs[~np.isnan(signs)]
    if len(signs) == 0:
        return None
    cur = signs[-1]
    if cur == 0:
        return None
    n = 0
    for v in signs[::-1]:
        if v == cur:
            n += 1
        else:
            break
    if n < MIN_STREAK:
        return None
    word = words[0] if cur > 0 else words[1]
    note = f"its {_ordinal(n)} straight {word}"

    # last time an equally long same-direction streak occurred, excluding the
    # current one
    valid = changes.dropna()
    run, last_end = 0, None
    sign_list = np.sign(valid.to_numpy(dtype=float))
    date_list = dates[changes.notna()].reset_index(drop=True)
    for i in range(len(sign_list) - n):
        if sign_list[i] == cur:
            run += 1
            if run >= n:
                last_end = date_list.iloc[i]
        else:
            run = 0
    if last_end is None:
        note += ", the longest such streak on record"
    elif _months_between(last_end, dates.iloc[-1]) >= MIN_GAP_MONTHS_MOVE:
        note += f", the longest such streak since {_month(last_end)}"
    return note


# the unemployment/housing/sentiment flags compare 3-month averages, so a
# flag can trip in a month where the raw number moved the other way; spelling
# out "3-month trend" keeps those sentences from reading as contradictions
TREND_FLAG_DIRECTION = {
    "unemployment_rate": "rising",
    "housing_starts": "falling",
    "consumer_sentiment": "falling",
}


def _flag_clause(indicator: str, activated: bool) -> str:
    trend = TREND_FLAG_DIRECTION.get(indicator)
    if trend:
        if activated:
            return f"; its 3-month trend is now {trend}, <strong>activating a stress flag</strong>"
        return f"; its 3-month trend is no longer {trend}, clearing a stress flag"
    if activated:
        return "; <strong>stress flag activated</strong>"
    return "; stress flag cleared"


def _tone(delta: float, bad_direction: int) -> str:
    if bad_direction == 0 or delta == 0 or pd.isna(delta):
        return "neutral"
    return "warn" if delta * bad_direction > 0 else "good"


def _join_notes(base: str, notes: list[str | None]) -> str:
    real = [n for n in notes if n]
    if not real:
        return base
    return base + ", " + "; ".join(real)


# --------------------------------------------------------------------------- #
# Per-indicator sentences
# --------------------------------------------------------------------------- #
def _series(hist: pd.DataFrame, col: str) -> pd.DataFrame:
    return hist[["date", col]].dropna().reset_index(drop=True)


def _unemployment(hist: pd.DataFrame) -> tuple[BriefingItem | None, bool]:
    s = _series(hist, "unemployment_rate")
    if len(s) < 2:
        return None, False
    cur, prv = s["unemployment_rate"].iloc[-1], s["unemployment_rate"].iloc[-2]
    delta = cur - prv
    changes = s["unemployment_rate"].diff()
    notes = [
        _streak_note(s["date"], changes),
        _move_note(s["date"], changes),
        _extreme_note(s["date"], s["unemployment_rate"]),
    ]
    verb = "rose" if delta > 0 else ("fell" if delta < 0 else "held")
    base = (
        f"<strong>Unemployment</strong> {verb} to {cur:.1f}%"
        + (f" (from {prv:.1f}%)" if delta != 0 else "")
    )
    notable = abs(delta) >= 0.1 or any(notes)
    return BriefingItem(_join_notes(base, notes), _tone(delta, +1)), notable


def _inflation(hist: pd.DataFrame) -> tuple[BriefingItem | None, bool]:
    s = _series(hist, "cpi")
    if len(s) < 14:
        return None, False
    yoy = (s["cpi"] / s["cpi"].shift(12) - 1) * 100
    cur, prv = yoy.iloc[-1], yoy.iloc[-2]
    if pd.isna(cur) or pd.isna(prv):
        return None, False
    delta = cur - prv
    # avoid "-0.0%" when inflation rounds to zero from below
    cur, prv = (0.0 if abs(v) < 0.05 else v for v in (cur, prv))
    notes = [_extreme_note(s["date"][yoy.notna()], yoy.dropna(), unit_word="rate")]
    verb = "picked up" if delta > 0 else ("cooled" if delta < 0 else "held")
    base = (
        f"<strong>CPI inflation</strong> {verb} to {cur:.1f}% year-over-year"
        + (f" (from {prv:.1f}%)" if delta != 0 else "")
    )
    notable = abs(delta) >= 0.15 or any(notes)
    return BriefingItem(_join_notes(base, notes), _tone(delta, +1)), notable


def _gdp(hist: pd.DataFrame, latest_date: pd.Timestamp) -> tuple[BriefingItem | None, bool]:
    s = _series(hist, "gdp")
    if len(s) < 2:
        return None, False
    obs_date = s["date"].iloc[-1]
    # only brief on GDP while its newest quarter is still fresh; after that
    # it's old news until the next print lands
    if _months_between(obs_date, latest_date) > 3:
        return None, False
    chg = hist[["date", "gdp_mom_pct"]].dropna().reset_index(drop=True) \
        if "gdp_mom_pct" in hist.columns else None
    if chg is None or chg.empty:
        return None, False
    cur_chg = chg["gdp_mom_pct"].iloc[-1]
    notes = [_move_note(chg["date"], chg["gdp_mom_pct"], period_word="quarterly")]
    verb = "grew" if cur_chg > 0 else "contracted"
    base = f"<strong>GDP</strong> {verb} {abs(cur_chg):.1f}% in {_quarter(obs_date)} (quarter-over-quarter)"
    notable = cur_chg < 0 or any(notes) or abs(cur_chg) >= 1.5
    return BriefingItem(_join_notes(base, notes), _tone(-cur_chg, +1)), notable


def _fed_funds(hist: pd.DataFrame) -> tuple[BriefingItem | None, bool]:
    s = _series(hist, "fed_funds_rate")
    if len(s) < 2:
        return None, False
    cur, prv = s["fed_funds_rate"].iloc[-1], s["fed_funds_rate"].iloc[-2]
    delta = cur - prv
    notes = [_extreme_note(s["date"], s["fed_funds_rate"])]
    verb = "rose" if delta > 0 else ("fell" if delta < 0 else "held")
    base = (
        f"<strong>The fed funds rate</strong> {verb} to {cur:.2f}%"
        + (f" (from {prv:.2f}%)" if abs(delta) >= 0.01 else "")
    )
    notable = abs(delta) >= 0.20 or any(notes)
    return BriefingItem(_join_notes(base, notes), "neutral"), notable


def _housing(hist: pd.DataFrame) -> tuple[BriefingItem | None, bool]:
    s = _series(hist, "housing_starts")
    if len(s) < 2:
        return None, False
    cur, prv = s["housing_starts"].iloc[-1], s["housing_starts"].iloc[-2]
    pct = (cur / prv - 1) * 100 if prv else 0.0
    pct_changes = s["housing_starts"].pct_change() * 100
    notes = [
        _streak_note(s["date"], s["housing_starts"].diff(),
                     words=("monthly rise", "monthly decline")),
        _move_note(s["date"], pct_changes),
        _extreme_note(s["date"], s["housing_starts"]),
    ]
    verb = "rose" if pct > 0 else ("fell" if pct < 0 else "held")
    base = f"<strong>Housing starts</strong> {verb} {abs(pct):.1f}% to {cur:,.0f}K (annualized)"
    notable = abs(pct) >= 3.0 or any(notes)
    return BriefingItem(_join_notes(base, notes), _tone(-pct, +1)), notable


def _sentiment(hist: pd.DataFrame) -> tuple[BriefingItem | None, bool]:
    s = _series(hist, "consumer_sentiment")
    if len(s) < 2:
        return None, False
    cur, prv = s["consumer_sentiment"].iloc[-1], s["consumer_sentiment"].iloc[-2]
    delta = cur - prv
    notes = [
        _streak_note(s["date"], s["consumer_sentiment"].diff()),
        _move_note(s["date"], s["consumer_sentiment"].diff()),
        _extreme_note(s["date"], s["consumer_sentiment"], unit_word="reading"),
    ]
    verb = "rose" if delta > 0 else ("fell" if delta < 0 else "held")
    base = (
        f"<strong>Consumer sentiment</strong> {verb} to {cur:.1f}"
        + (f" (from {prv:.1f})" if delta != 0 else "")
    )
    notable = abs(delta) >= 2.5 or any(notes)
    return BriefingItem(_join_notes(base, notes), _tone(delta, -1)), notable


def _yield_spread(hist: pd.DataFrame) -> tuple[BriefingItem | None, bool]:
    if "yield_spread" not in hist.columns:
        return None, False
    s = _series(hist, "yield_spread")
    if len(s) < 2:
        return None, False
    cur, prv = s["yield_spread"].iloc[-1], s["yield_spread"].iloc[-2]
    delta = cur - prv
    notes = [_extreme_note(s["date"], s["yield_spread"], unit_word="reading")]
    if prv >= 0 > cur:
        notes.insert(0, "the curve has inverted")
    elif cur >= 0 > prv:
        notes.insert(0, "the curve is no longer inverted")
    verb = "widened" if delta > 0 else ("narrowed" if delta < 0 else "held")
    base = (
        f"<strong>The 10Y-3M yield spread</strong> {verb} to {cur:+.2f}pt"
        + (f" (from {prv:+.2f}pt)" if delta != 0 else "")
    )
    notable = abs(delta) >= 0.15 or any(notes) or (prv >= 0) != (cur >= 0)
    return BriefingItem(_join_notes(base, notes), _tone(delta, -1)), notable


# --------------------------------------------------------------------------- #
# Builder
# --------------------------------------------------------------------------- #
def build_briefing(df: pd.DataFrame) -> Briefing | None:
    core = [c for c in MONTHLY_CORE if c in df.columns]
    complete = df.dropna(subset=core) if core else df
    if len(complete) < 2:
        return None
    latest_date = pd.Timestamp(complete["date"].iloc[-1])
    prev_date = pd.Timestamp(complete["date"].iloc[-2])
    # superlative scans stop at the latest complete month, so a half-published
    # newer month can't sneak into "on record" comparisons
    hist = df[df["date"] <= latest_date]

    builders = {
        "unemployment_rate": lambda: _unemployment(hist),
        "cpi": lambda: _inflation(hist),
        "gdp": lambda: _gdp(hist, latest_date),
        "fed_funds_rate": lambda: _fed_funds(hist),
        "housing_starts": lambda: _housing(hist),
        "consumer_sentiment": lambda: _sentiment(hist),
        "yield_spread": lambda: _yield_spread(hist),
    }

    latest_row = complete.iloc[-1]
    prev_row = complete.iloc[-2]
    flipped: dict[str, bool] = {}  # indicator -> flag turned on?
    for flag, indicator in FLAG_TO_INDICATOR.items():
        if flag in df.columns:
            now, before = bool(latest_row.get(flag)), bool(prev_row.get(flag))
            if now != before:
                flipped[indicator] = now
    # the GDP flag rides on a quarterly series: in months with no new GDP
    # print it evaluates false, which looks like a "cleared" flip that never
    # actually happened. Only mention it when a fresh quarter landed.
    if "gdp" in flipped and pd.isna(latest_row.get("gdp_mom_pct")):
        del flipped["gdp"]

    items: list[BriefingItem] = []
    quiet: list[str] = []
    for indicator, build in builders.items():
        result, notable = build()
        if result is None:
            continue
        if indicator in flipped:
            result.text += _flag_clause(indicator, flipped[indicator])
            if flipped[indicator]:
                result.tone = "warn"
            notable = True
        if notable:
            items.append(result)
        else:
            quiet.append(QUIET_LABELS[indicator])

    score_now = int(latest_row.get("signal_score", 0))
    score_before = int(prev_row.get("signal_score", 0))
    watch_now = bool(latest_row.get("recession_watch", False))
    watch_before = bool(prev_row.get("recession_watch", False))
    if score_now > score_before:
        move = f", up from {score_before}"
    elif score_now < score_before:
        move = f", down from {score_before}"
    else:
        move = ", unchanged"
    watch_bit = f"Recession watch is {'on' if watch_now else 'off'}."
    if watch_now != watch_before:
        watch_bit = f"<strong>Recession watch switched {'ON' if watch_now else 'OFF'} this month.</strong>"
    score_item = BriefingItem(
        f"<strong>Signal score: {score_now} of 7</strong>{move}. {watch_bit}",
        "warn" if watch_now or score_now > score_before else ("good" if score_now < score_before else "neutral"),
    )

    return Briefing(
        latest_label=_month(latest_date),
        previous_label=_month(prev_date),
        items=items,
        quiet=quiet,
        score_item=score_item,
    )
