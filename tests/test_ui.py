import re

import pandas as pd
import pytest

import theme
import ui

HOSTILE = '<script>alert("x")</script> $5 & $6\nsecond line'
BLOCK_TAGS = ("<div", "<section", "<header", "<footer", "<nav")


def _assert_single_line(out: str) -> None:
    assert "\n" not in out and "\r" not in out


# --------------------------------------------------------------------- esc --
def test_esc_escapes_markup_dollars_and_newlines():
    assert ui.esc(HOSTILE) == (
        "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &#36;5 &amp; &#36;6 second line"
    )


# --------------------------------------------------------------------- CSS --
@pytest.mark.parametrize("mode", ["light", "dark"])
def test_css_has_no_testid_selectors_and_has_the_focus_ring(mode):
    css = ui.build_css(mode)
    assert "data-testid" not in css
    assert f"outline:3px solid {theme.FOCUS}" in css
    assert css.startswith("<style>") and css.endswith("</style>")


def test_css_carries_both_token_sets_through_light_dark():
    css = ui.build_css("light")
    for key in theme.LIGHT:
        var = "--civic-" + key.lower().replace("_", "-")
        assert f"{var}:light-dark({theme.LIGHT[key]}, {theme.DARK[key]})" in css
    assert "@supports (color: light-dark(#000, #fff))" in css


def test_css_fallback_follows_the_selected_mode():
    assert ":root{--civic-page:#151b22;" in ui.build_css("dark")
    assert ":root{--civic-page:#ffffff;" in ui.build_css("light")


def test_css_has_series_variables_and_classes():
    css = ui.build_css("light")
    for i, (light, dark) in enumerate(zip(theme.SERIES["light"], theme.SERIES["dark"])):
        assert f"--civic-series-{i}:light-dark({light}, {dark})" in css
        assert f".civic-spark-{i} .civic-spark-line{{stroke:var(--civic-series-{i})}}" in css
        assert f".civic-swatch-{i}{{background:var(--civic-series-{i})}}" in css


def test_css_only_styles_the_apps_own_classes():
    classes = set(re.findall(r"\.([a-zA-Z][\w-]*)", ui.build_css("light")))
    assert classes, "expected class selectors"
    assert all(c.startswith(("civic-", "st-key-civic")) for c in classes), sorted(classes)
    assert f".st-key-{ui.PAGE_CONTAINER_KEY}" in ui.build_css("light")


# ------------------------------------------------------- block helpers -------
def _block_outputs() -> dict[str, str]:
    return {
        "masthead": ui.masthead(),
        "breadcrumbs": ui.breadcrumbs(HOSTILE),
        "title_block": ui.title_block(HOSTILE, HOSTILE, HOSTILE),
        "page_header": ui.page_header(HOSTILE, HOSTILE, HOSTILE),
        "section": ui.section(HOSTILE),
        "sidebar_label": ui.sidebar_label(HOSTILE),
        "signal_banner": ui.signal_banner(5, "watch", HOSTILE, HOSTILE, [HOSTILE], HOSTILE),
        "briefing": ui.briefing(HOSTILE, HOSTILE, [("<strong>ok</strong>", "warn")], [HOSTILE]),
        "tile_grid": ui.tile_grid([ui.Tile(HOSTILE, HOSTILE, change=HOSTILE, delta=1.0, tone="bad", caption=HOSTILE)]),
        "glossary": ui.glossary([(0, HOSTILE, HOSTILE, HOSTILE)]),
        "footer": ui.footer(HOSTILE, HOSTILE),
    }


@pytest.mark.parametrize("name", list(_block_outputs()))
def test_block_helpers_return_one_escaped_line_in_a_block_tag(name):
    out = _block_outputs()[name]
    _assert_single_line(out)
    assert out.startswith(BLOCK_TAGS), out[:40]
    assert "<script>" not in out
    assert "data-testid" not in out
    for inner in ("<p", "<ul", "<ol", "<li", "<h1", "<h2"):
        assert inner not in out, inner


def test_masthead_and_breadcrumbs():
    assert ui.masthead() == '<header class="civic-masthead">US Economic Indicators</header>'
    crumbs = ui.breadcrumbs("State by state")
    assert '<nav class="civic-crumbs" aria-label="Breadcrumb">' in crumbs
    assert '<a class="civic-link" href="./" target="_self">Home</a>' in crumbs
    assert '<span role="listitem" aria-current="page">State by state</span>' in crumbs


def test_title_block_marks_the_heading_and_skips_an_empty_meta():
    out = ui.title_block("Data revisions", "Lede.")
    assert '<div class="civic-title" role="heading" aria-level="1">Data revisions</div>' in out
    assert "civic-meta" not in out
    assert '<div class="civic-meta">Updated</div>' in ui.title_block("T", "L", "Updated")


def test_page_header_combines_masthead_crumbs_and_title():
    out = ui.page_header("National overview", "Lede.", "Data through Sep 2026")
    assert out.startswith('<div class="civic-header"><header class="civic-masthead">')
    assert 'aria-current="page">National overview</span>' in out
    assert 'aria-level="1">National overview</div>' in out


def test_section_is_a_level_two_heading():
    assert ui.section("Latest readings") == (
        '<div class="civic-section" role="heading" aria-level="2">Latest readings</div>'
    )


@pytest.mark.parametrize("status", ["good", "bad", "caution", "neutral"])
def test_tag_classes(status):
    assert ui.tag("A & B", status) == f'<strong class="civic-tag civic-tag--{status}">A &amp; B</strong>'


def test_tag_rejects_unknown_status():
    with pytest.raises(ValueError):
        ui.tag("x", "purple")


@pytest.mark.parametrize("status, css", [("watch", "bad"), ("elevated", "caution"), ("clear", "good")])
def test_signal_banner_status_tags(status, css):
    out = ui.signal_banner(3, status, "Label", "Sep 2026", [], "Note.")
    assert f'civic-tag civic-tag--{css}">Label</strong>' in out
    assert '<div class="civic-score">3 <small>of 7</small></div>' in out
    assert '<div class="civic-asof">as of Sep 2026</div>' in out
    assert "No active stress signals. Conditions appear stable." in out


def test_signal_banner_lists_active_flags():
    out = ui.signal_banner(4, "watch", "Recession watch", "Sep 2026", ["GDP contracting", "Yield curve inverted"], "N")
    assert out.count('<div class="civic-flag" role="listitem">') == 2
    assert "No active stress signals" not in out


def test_signal_banner_rejects_unknown_status():
    with pytest.raises(ValueError):
        ui.signal_banner(1, "calm", "x", "", [], "")


@pytest.mark.parametrize(
    "names, sentence",
    [([], ""), (["GDP"], "Little change in GDP."), (["GDP", "CPI"], "Little change in GDP and CPI."),
     (["a", "b", "c"], "Little change in a, b and c.")],
)
def test_quiet_sentence(names, sentence):
    assert ui.quiet_sentence(names) == sentence


def test_briefing_keeps_trusted_markup_and_maps_tones():
    out = ui.briefing("Sep 2026", "Aug 2026",
                      [("<strong>Signal score: 2 of 7</strong>, unchanged.", "neutral"),
                       ("<strong>Housing</strong> fell", "warn"), ("<strong>GDP</strong> grew", "good")],
                      ["inflation"])
    assert "<strong>Signal score: 2 of 7</strong>, unchanged." in out
    assert "civic-dot civic-dot--neutral" in out
    assert "civic-dot civic-dot--bad" in out
    assert "civic-dot civic-dot--good" in out
    assert '<span class="civic-brief-vs">vs Aug 2026 · written automatically from each data refresh</span>' in out
    assert '<div class="civic-brief-quiet">Little change in inflation.</div>' in out
    assert "civic-brief-quiet" not in ui.briefing("a", "b", [], [])


def test_tile_grid_renders_arrow_tone_caption_and_columns():
    out = ui.tile_grid([
        ui.Tile("CPI", "322.0", change="+0.31% MoM", delta=0.31, tone="bad", caption="as of Aug 2026"),
        ui.Tile("GDP", "N/A"),
        ui.Tile("Largest single revision", "-1.2pp", change="Q4 2008", show_arrow=False),
    ], columns=3)
    assert out.startswith('<div class="civic-tiles" role="list" style="--civic-cols:3">')
    assert out.count('<div class="civic-tile" role="listitem">') == 3
    assert '<div class="civic-tile-change civic-bad"><span aria-hidden="true">\u25b2 </span>+0.31% MoM</div>' in out
    assert '<div class="civic-tile-caption">as of Aug 2026</div>' in out
    assert '<div class="civic-tile-change" aria-hidden="true">&nbsp;</div>' in out
    assert '<div class="civic-tile-change civic-neutral">Q4 2008</div>' in out


def test_tile_rejects_unknown_tone():
    with pytest.raises(ValueError):
        ui.tile_grid([ui.Tile("x", "1", change="+1", delta=1.0, tone="great")])


def test_sparkline_svg_scales_points_into_the_viewbox():
    out = ui.sparkline_svg([1.0, 2.0, 3.0], slot=4)
    _assert_single_line(out)
    assert out.startswith('<svg class="civic-spark civic-spark-4" viewBox="0 0 100 28"')
    assert 'aria-hidden="true"' in out
    assert 'points="0.00,26.00 50.00,14.00 100.00,2.00"' in out
    assert 'points="0,28 0.00,26.00 50.00,14.00 100.00,2.00 100,28"' in out


def test_sparkline_svg_skips_nan_and_handles_flat_and_short_series():
    assert ui.sparkline_svg([], 0) == ""
    assert ui.sparkline_svg([5.0], 0) == ""
    assert 'points="0.00,26.00 100.00,2.00"' in ui.sparkline_svg([1.0, float("nan"), 3.0], 0)
    assert 'points="0.00,26.00 100.00,26.00"' in ui.sparkline_svg([5.0, 5.0], 0)


def test_glossary_entry_has_swatch_and_texts():
    out = ui.glossary([(2, "U-6", "What it is.", "Context.")])
    assert '<span class="civic-swatch civic-swatch-2" aria-hidden="true"></span>' in out
    assert '<div class="civic-glossary-name">U-6</div>' in out
    assert '<div class="civic-glossary-what">What it is.</div>' in out
    assert '<div class="civic-glossary-context">Context.</div>' in out


def test_footer():
    assert ui.footer("Left", "Right") == '<footer class="civic-footer"><span>Left</span><span>Right</span></footer>'


def test_nullable_pandas_values_do_not_raise():
    # pd.NA / NaN deltas and sparkline points come straight from nullable columns
    for missing in (pd.NA, float("nan"), None):
        out = ui.tile_grid([ui.Tile("x", "1", change="+1", delta=missing)])
        assert "▬ " in out
    assert 'points="0.00,26.00 100.00,2.00"' in ui.sparkline_svg([1.0, pd.NA, None, 3.0], 0)
    assert ui.sparkline_svg([pd.NA, 1.0], 0) == ""


def test_sparkline_svg_drops_infinite_values():
    out = ui.sparkline_svg([1.0, float("inf"), 3.0, float("-inf")], 0)
    assert "nan" not in out and "inf" not in out
    assert 'points="0.00,26.00 100.00,2.00"' in out
    assert ui.sparkline_svg([float("inf"), 1.0], 0) == ""


def test_every_tile_has_five_child_blocks():
    # label, value, change, caption and spark slot, so a subgrid lines up
    # across tiles whatever each one leaves out
    tiles = [
        ui.Tile("Bare", "1"),
        ui.Tile("Caption only", "2", caption="a caption"),
        ui.Tile("Full", "3", change="+1", delta=1.0, tone="good", caption="c", spark=ui.sparkline_svg([1.0, 2.0], 0)),
        ui.Tile("No arrow", "4", change="Q1", show_arrow=False),
    ]
    for tile in tiles:
        out = ui._tile(tile)
        inner = out[len('<div class="civic-tile" role="listitem">'):-len("</div>")]
        # top-level children only: track nesting depth over div/svg tags
        depth, children = 0, 0
        for m in re.finditer(r"<(/?)(div|svg)\b[^>]*?(/?)>", inner):
            closing, selfclosing = m.group(1), m.group(3)
            if not closing:
                if depth == 0:
                    children += 1
                if not selfclosing:
                    depth += 1
            else:
                depth -= 1
        assert children == 5, (tile.label, children)
    assert '<div class="civic-spark-slot" aria-hidden="true"></div>' in ui._tile(tiles[0])
    assert '<div class="civic-tile-caption"></div>' in ui._tile(tiles[0])


def test_css_rounds_nothing_on_the_keyed_widgets():
    css = ui.build_css("light")
    assert ".st-key-civic_indicators button{border-radius:0}" in css
    assert ".st-key-civic_tm_slider *{border-radius:0}" in css
    assert "@supports (grid-template-rows: subgrid)" in css
