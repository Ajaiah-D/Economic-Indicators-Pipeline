"""
HTML and CSS for the dashboard's "Civic" layout.

Every helper returns ONE line of HTML: st.markdown treats a blank line inside
HTML as the end of the block and an indented line as a code block. All
dynamic text goes through esc(). Each block helper's outer tag is a
CommonMark block tag (div, section, header, footer, nav), so Markdown never
parses inside it. Text lines are div/span with ARIA roles rather than
p/ul/li/h1, because Streamlit's Markdown styles those tags with higher
specificity than a class (and adds anchor links to headings).

The CSS styles only the civic-* classes emitted here and the page
container's st-key-civic_page class. It never targets Streamlit's internal
test ids or other internal classes, which change between releases.
"""

from __future__ import annotations

import html
from dataclasses import dataclass

import pandas as pd

import theme

PAGE_CONTAINER_KEY = "civic_page"
MASTHEAD_LABEL = "US Economic Indicators"

TAG_STATUSES = ("good", "bad", "caution", "neutral")
BANNER_STATUS = {"watch": "bad", "elevated": "caution", "clear": "good"}
TONE_CLASS = {"warn": "bad", "good": "good", "neutral": "neutral"}
TILE_TONES = ("good", "bad", "neutral")


def esc(value: object) -> str:
    """HTML-escape text. Also escapes `$` (Streamlit's Markdown reads $...$
    as LaTeX) and folds newlines so the result stays on one line."""
    text = html.escape(str(value), quote=True).replace("$", "&#36;")
    return text.replace("\r", " ").replace("\n", " ")


def _one_line(markup: str) -> str:
    return markup.replace("\r", " ").replace("\n", " ")


# --------------------------------------------------------------------------- #
# CSS
# --------------------------------------------------------------------------- #
def _var(token: str) -> str:
    return "--civic-" + token.lower().replace("_", "-")


_RULES = (
    f".st-key-{PAGE_CONTAINER_KEY}{{max-width:1440px;width:100%;margin-left:auto;margin-right:auto}}"
    # the masthead sits just under Streamlit's toolbar: the main block has 6rem
    # of top padding, the toolbar is about 3.75rem tall
    ".civic-masthead{background:var(--civic-ribbon);color:#ffffff;font-weight:700;font-size:1.05rem;"
    "letter-spacing:0.01em;padding:0.75rem 1rem;margin:-2rem 0 0 0;border-bottom:4px solid var(--civic-tile-rule)}"
    ".civic-crumbs{background:var(--civic-surface);color:var(--civic-ink);font-size:0.9rem;padding:0.55rem 1rem}"
    ".civic-crumbs-list{display:flex;flex-wrap:wrap;gap:0.4rem}"
    ".civic-crumbs-list>span+span::before{content:\"\u203a\";color:var(--civic-ink-2);margin-right:0.4rem}"
    "a.civic-link{color:var(--civic-accent);text-decoration:underline;text-underline-offset:0.15em}"
    "a.civic-link:hover{text-decoration-thickness:3px}"
    f"a.civic-link:focus,a.civic-link:focus-visible{{outline:3px solid {theme.FOCUS};outline-offset:0;"
    f"background-color:{theme.FOCUS};color:#0b0c0c;text-decoration:none;box-shadow:0 4px #0b0c0c}}"
    ".civic-title{color:var(--civic-heading);font-size:2.25rem;font-weight:700;line-height:1.15;margin:1.4rem 0 0.5rem 0}"
    ".civic-lede{color:var(--civic-ink);font-size:1.1rem;line-height:1.5;max-width:48rem;margin:0 0 0.3rem 0}"
    ".civic-meta{color:var(--civic-ink-2);font-size:0.9rem;margin:0 0 0.6rem 0}"
    ".civic-section{color:var(--civic-heading);font-size:1.25rem;font-weight:700;margin:0.3rem 0 0.6rem 0}"
    ".civic-sidebar-label{color:var(--civic-heading);font-size:1rem;font-weight:700;margin:0 0 0.3rem 0}"
    ".civic-tag{display:inline-block;border:2px solid currentColor;padding:0.15rem 0.5rem;font-size:0.85rem;"
    "font-weight:700;letter-spacing:0.05em;text-transform:uppercase}"
    ".civic-tag--good{color:var(--civic-good)}.civic-tag--bad{color:var(--civic-bad)}"
    ".civic-tag--caution{color:var(--civic-caution)}.civic-tag--neutral{color:var(--civic-neutral)}"
    ".civic-banner{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,2.3fr);gap:2rem;"
    "border-top:2px solid var(--civic-heading);border-bottom:1px solid var(--civic-border);padding:1rem 0 1.2rem 0}"
    ".civic-kicker{color:var(--civic-ink-2);font-size:0.85rem;font-weight:700;letter-spacing:0.06em;"
    "text-transform:uppercase;margin:0}"
    ".civic-score{color:var(--civic-heading);font-size:3.2rem;font-weight:700;line-height:1;margin:0.4rem 0 0.7rem 0}"
    ".civic-score small{color:var(--civic-ink-2);font-size:1.3rem;font-weight:400}"
    ".civic-asof{color:var(--civic-ink-2);font-size:0.85rem;margin:0.7rem 0 0 0}"
    ".civic-flags{display:flex;flex-wrap:wrap;gap:0.4rem;margin:0.5rem 0 0 0}"
    ".civic-flag{background:var(--civic-surface);border-left:4px solid var(--civic-bad);color:var(--civic-ink);"
    "font-size:0.92rem;padding:0.35rem 0.65rem}"
    ".civic-allclear{display:inline-block;background:var(--civic-surface);border-left:4px solid var(--civic-good);"
    "color:var(--civic-ink);font-size:0.92rem;padding:0.35rem 0.65rem;margin:0.5rem 0 0 0}"
    ".civic-note{color:var(--civic-ink-2);font-size:0.85rem;line-height:1.5;margin:0.85rem 0 0 0}"
    ".civic-brief{background:var(--civic-surface);border-left:4px solid var(--civic-tile-rule);padding:1rem 1.25rem}"
    ".civic-brief-head{display:flex;flex-wrap:wrap;align-items:baseline;gap:0.6rem;margin:0 0 0.6rem 0}"
    ".civic-brief-title{color:var(--civic-heading);font-size:1.05rem;font-weight:700}"
    ".civic-brief-vs{color:var(--civic-ink-2);font-size:0.85rem}"
    ".civic-brief-item{display:flex;align-items:flex-start;gap:0.6rem;color:var(--civic-ink);font-size:0.95rem;"
    "line-height:1.55;margin:0.4rem 0}"
    ".civic-brief-item strong{font-weight:700}"
    ".civic-dot{display:inline-block;flex:none;width:10px;height:10px;margin-top:0.45rem}"
    ".civic-dot--good{background:var(--civic-good)}.civic-dot--bad{background:var(--civic-bad)}"
    ".civic-dot--neutral{background:var(--civic-neutral)}"
    ".civic-brief-quiet{color:var(--civic-ink-2);font-size:0.88rem;margin:0.55rem 0 0 0}"
    ".civic-tiles{display:grid;grid-template-columns:repeat(var(--civic-cols,3),minmax(0,1fr));gap:1rem}"
    ".civic-tile{display:flex;flex-direction:column;min-width:0;background:var(--civic-surface);"
    "border-bottom:3px solid var(--civic-tile-rule);padding:0.85rem 1rem 0.7rem 1rem}"
    ".civic-tile-label{color:var(--civic-ink-2);font-size:0.9rem;font-weight:700}"
    ".civic-tile-value{color:var(--civic-ink);font-size:1.9rem;font-weight:700;line-height:1.2;margin:0.25rem 0 0.15rem 0}"
    ".civic-tile-change{font-size:0.92rem;font-weight:700}"
    ".civic-good{color:var(--civic-good)}.civic-bad{color:var(--civic-bad)}.civic-neutral{color:var(--civic-neutral)}"
    ".civic-tile-caption{color:var(--civic-ink-2);font-size:0.8rem;margin:0.2rem 0 0.45rem 0}"
    ".civic-spark{display:block;width:100%;height:44px;margin-top:auto}"
    ".civic-spark-line{fill:none;stroke-width:2;vector-effect:non-scaling-stroke}"
    ".civic-spark-area{stroke:none;opacity:0.1}"
    ".civic-glossary-item{display:flex;gap:0.7rem;margin:0 0 1.1rem 0}"
    ".civic-swatch{display:inline-block;flex:none;width:10px;height:10px;margin-top:0.4rem}"
    ".civic-glossary-name{color:var(--civic-heading);font-weight:700}"
    ".civic-glossary-what{color:var(--civic-ink);font-size:0.92rem;line-height:1.5;margin:0.15rem 0 0 0}"
    ".civic-glossary-context{color:var(--civic-ink-2);font-size:0.88rem;line-height:1.5;margin:0.3rem 0 0 0}"
    ".civic-footer{display:flex;flex-wrap:wrap;justify-content:space-between;gap:0.5rem;"
    "border-top:1px solid var(--civic-border);color:var(--civic-ink-2);font-size:0.85rem;margin-top:2rem;padding-top:1rem}"
    "@media (max-width:900px){.civic-tiles{grid-template-columns:repeat(2,minmax(0,1fr))}}"
    "@media (max-width:640px){.civic-tiles{grid-template-columns:minmax(0,1fr)}"
    ".civic-banner{grid-template-columns:minmax(0,1fr);gap:1rem}.civic-title{font-size:1.75rem}}"
)


def _series_rules() -> str:
    return "".join(
        f".civic-spark-{i} .civic-spark-line{{stroke:var(--civic-series-{i})}}"
        f".civic-spark-{i} .civic-spark-area{{fill:var(--civic-series-{i})}}"
        f".civic-swatch-{i}{{background:var(--civic-series-{i})}}"
        for i in range(len(theme.SERIES["light"]))
    )


def build_css(theme_mode: str | None = None) -> str:
    """The page stylesheet, for st.html (style-only st.html takes no layout
    space). Variables resolve through CSS light-dark(), so the app's HTML
    follows Streamlit's active theme the moment it changes; browsers without
    light-dark() get the set selected for this run."""
    chosen = theme.tokens(theme_mode)
    plain = [f"{_var(k)}:{chosen[k]}" for k in theme.LIGHT]
    plain += [f"--civic-series-{i}:{c}" for i, c in enumerate(theme.series_palette(theme_mode))]
    adaptive = [f"{_var(k)}:light-dark({theme.LIGHT[k]}, {theme.DARK[k]})" for k in theme.LIGHT]
    adaptive += [
        f"--civic-series-{i}:light-dark({light}, {dark})"
        for i, (light, dark) in enumerate(zip(theme.SERIES["light"], theme.SERIES["dark"]))
    ]
    return (
        "<style>"
        ":root{" + ";".join(plain) + "}"
        "@supports (color: light-dark(#000, #fff)){:root{" + ";".join(adaptive) + "}}"
        + _RULES + _series_rules()
        + "</style>"
    )


# --------------------------------------------------------------------------- #
# Page header
# --------------------------------------------------------------------------- #
def masthead() -> str:
    return f'<header class="civic-masthead">{esc(MASTHEAD_LABEL)}</header>'


def breadcrumbs(page: str) -> str:
    # "./" is relative, so it also works under Community Cloud's path prefix;
    # target="_self" keeps the click in this tab
    return (
        '<nav class="civic-crumbs" aria-label="Breadcrumb"><div class="civic-crumbs-list" role="list">'
        '<span role="listitem"><a class="civic-link" href="./" target="_self">Home</a></span>'
        f'<span role="listitem" aria-current="page">{esc(page)}</span></div></nav>'
    )


def title_block(title: str, lede: str, meta: str = "") -> str:
    meta_html = f'<div class="civic-meta">{esc(meta)}</div>' if meta else ""
    return (
        f'<div class="civic-titleblock"><div class="civic-title" role="heading" aria-level="1">{esc(title)}</div>'
        f'<div class="civic-lede">{esc(lede)}</div>{meta_html}</div>'
    )


def page_header(page: str, lede: str, meta: str = "") -> str:
    """Masthead ribbon, "Home › <page>" band, then the page title and lede."""
    return f'<div class="civic-header">{masthead()}{breadcrumbs(page)}{title_block(page, lede, meta)}</div>'


def section(label: str) -> str:
    return f'<div class="civic-section" role="heading" aria-level="2">{esc(label)}</div>'


def sidebar_label(label: str) -> str:
    return f'<div class="civic-sidebar-label">{esc(label)}</div>'


# --------------------------------------------------------------------------- #
# Signal banner and briefing
# --------------------------------------------------------------------------- #
def tag(text: str, status: str) -> str:
    if status not in TAG_STATUSES:
        raise ValueError(f"unknown tag status {status!r}")
    return f'<strong class="civic-tag civic-tag--{status}">{esc(text)}</strong>'


def signal_banner(score: int, status: str, label: str, as_of: str, active: list[str], note: str) -> str:
    if status not in BANNER_STATUS:
        raise ValueError(f"unknown banner status {status!r}")
    if active:
        flags = (
            '<div class="civic-flags" role="list">'
            + "".join(f'<div class="civic-flag" role="listitem">{esc(f)}</div>' for f in active)
            + "</div>"
        )
    else:
        flags = '<div class="civic-allclear">No active stress signals. Conditions appear stable.</div>'
    as_of_html = f'<div class="civic-asof">as of {esc(as_of)}</div>' if as_of else ""
    return (
        '<section class="civic-banner" aria-label="Recession-risk signal">'
        '<div><div class="civic-kicker">Recession-risk signal</div>'
        f'<div class="civic-score">{int(score)} <small>of 7</small></div>'
        f"{tag(label, BANNER_STATUS[status])}{as_of_html}</div>"
        '<div><div class="civic-kicker">Active stress signals</div>'
        f'{flags}<div class="civic-note">{esc(note)}</div></div></section>'
    )


def quiet_sentence(names: list[str]) -> str:
    if not names:
        return ""
    joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return f"Little change in {joined}."


def briefing(latest_label: str, previous_label: str, items: list[tuple[str, str]], quiet: list[str]) -> str:
    """items are (html_text, tone). html_text is TRUSTED markup from
    briefing.py (it carries <strong> emphasis) and is not escaped; every
    other argument is."""
    rows = "".join(
        f'<div class="civic-brief-item" role="listitem"><span class="civic-dot civic-dot--{TONE_CLASS[tone]}"'
        f' aria-hidden="true"></span><span>{_one_line(text)}</span></div>'
        for text, tone in items
    )
    quiet_html = f'<div class="civic-brief-quiet">{esc(quiet_sentence(quiet))}</div>' if quiet else ""
    return (
        '<section class="civic-brief" aria-label="This month in brief"><div class="civic-brief-head">'
        f'<span class="civic-brief-title">{esc(latest_label)}</span>'
        f'<span class="civic-brief-vs">vs {esc(previous_label)} · written automatically from each data refresh</span>'
        f'</div><div class="civic-brief-list" role="list">{rows}</div>{quiet_html}</section>'
    )


# --------------------------------------------------------------------------- #
# Stat tiles
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Tile:
    label: str
    value: str
    change: str | None = None  # e.g. "+0.31% MoM"; None = no change line
    delta: float | None = None  # signed change, picks the arrow
    tone: str = "neutral"  # "good" | "bad" | "neutral" (theme.change_tone)
    show_arrow: bool = True
    caption: str = ""  # e.g. "as of Aug 2026 · 3rd lowest of 51"
    spark: str = ""  # trusted SVG from sparkline_svg()


def _tile(t: Tile) -> str:
    if t.tone not in TILE_TONES:
        raise ValueError(f"unknown tile tone {t.tone!r}")
    if t.change is None:
        # keeps the row structure identical across tiles
        change = '<div class="civic-tile-change" aria-hidden="true">&nbsp;</div>'
    else:
        arrow = f'<span aria-hidden="true">{theme.arrow(None if pd.isna(t.delta) else t.delta)} </span>' if t.show_arrow else ""
        change = f'<div class="civic-tile-change civic-{t.tone}">{arrow}{esc(t.change)}</div>'
    caption = f'<div class="civic-tile-caption">{esc(t.caption)}</div>' if t.caption else ""
    return (
        f'<div class="civic-tile" role="listitem"><div class="civic-tile-label">{esc(t.label)}</div>'
        f'<div class="civic-tile-value">{esc(t.value)}</div>{change}{caption}{t.spark}</div>'
    )


def tile_grid(tiles: list[Tile], columns: int = 3) -> str:
    """ONE CSS-grid block, so tiles in a row share a height with no
    Streamlit-internal selectors; sparklines sit at each tile's foot."""
    return (
        f'<div class="civic-tiles" role="list" style="--civic-cols:{int(columns)}">'
        + "".join(_tile(t) for t in tiles)
        + "</div>"
    )


def sparkline_svg(values: list[float], slot: int) -> str:
    """Inline SVG sparkline coloured by series slot through CSS, so it
    follows the theme without a rerun. The y range is the data's own min-max."""
    points = [float(v) for v in values if not pd.isna(v)]
    if len(points) < 2:
        return ""
    lo, hi = min(points), max(points)
    span = (hi - lo) or 1.0
    last = len(points) - 1
    line = " ".join(f"{i * 100 / last:.2f},{26 - (v - lo) / span * 24:.2f}" for i, v in enumerate(points))
    return (
        f'<svg class="civic-spark civic-spark-{int(slot)}" viewBox="0 0 100 28" preserveAspectRatio="none"'
        ' aria-hidden="true" focusable="false">'
        f'<polygon class="civic-spark-area" points="0,28 {line} 100,28"></polygon>'
        f'<polyline class="civic-spark-line" points="{line}"></polyline></svg>'
    )


# --------------------------------------------------------------------------- #
# Glossary and footer
# --------------------------------------------------------------------------- #
def glossary(entries: list[tuple[int, str, str, str]]) -> str:
    items = "".join(
        f'<div class="civic-glossary-item"><span class="civic-swatch civic-swatch-{int(slot)}" aria-hidden="true"></span>'
        f'<div><div class="civic-glossary-name">{esc(name)}</div><div class="civic-glossary-what">{esc(what)}</div>'
        f'<div class="civic-glossary-context">{esc(context)}</div></div></div>'
        for slot, name, what, context in entries
    )
    return f'<div class="civic-glossary">{items}</div>'


def footer(left: str, right: str) -> str:
    return f'<footer class="civic-footer"><span>{esc(left)}</span><span>{esc(right)}</span></footer>'
