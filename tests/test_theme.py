import tomllib
from pathlib import Path

import pytest

import theme

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / ".streamlit" / "config.toml"

# The spec's token table, verbatim, plus CAUTION (the banner's amber middle step).
SPEC_LIGHT = {
    "PAGE": "#ffffff",
    "SURFACE": "#f3f3f3",
    "RIBBON": "#2e3f52",
    "HEADING": "#2e3f52",
    "INK": "#0b0c0c",
    "INK_2": "#505a5f",
    "BORDER": "#cdd3d9",
    "ACCENT": "#2b5f8a",
    "TILE_RULE": "#5b7a96",
    "GOOD": "#00703c",
    "BAD": "#c2361f",
    "NEUTRAL": "#505a5f",
    "CAUTION": "#8a5a00",
}
SPEC_DARK = {
    "PAGE": "#151b22",
    "SURFACE": "#1e2630",
    "RIBBON": "#0f141a",
    "HEADING": "#eef1f4",
    "INK": "#eef1f4",
    "INK_2": "#a8b3bf",
    "BORDER": "#3a4652",
    "ACCENT": "#9fc1e0",
    "TILE_RULE": "#8fa9c2",
    "GOOD": "#5cc98f",
    "BAD": "#ff8a78",
    "NEUTRAL": "#a8b3bf",
    "CAUTION": "#e0a43a",
}

# config.toml option -> theme token, for [theme.<mode>] and [theme.<mode>.sidebar]
MAIN_ROLES = {
    "primaryColor": "ACCENT",
    "backgroundColor": "PAGE",
    "secondaryBackgroundColor": "SURFACE",
    "textColor": "INK",
    "linkColor": "ACCENT",
    "borderColor": "BORDER",
}
SIDEBAR_ROLES = {
    "backgroundColor": "SURFACE",
    "secondaryBackgroundColor": "PAGE",
    "textColor": "INK",
    "borderColor": "BORDER",
}


def _config() -> dict:
    with CONFIG.open("rb") as fh:
        return tomllib.load(fh)


def test_token_sets_have_identical_keys():
    assert list(theme.LIGHT) == list(theme.DARK)


def test_tokens_match_the_spec():
    assert theme.LIGHT == SPEC_LIGHT
    assert theme.DARK == SPEC_DARK
    assert theme.FONT == "Arial, Helvetica, sans-serif"
    assert theme.FOCUS == "#ffdd00"


@pytest.mark.parametrize(
    "reported, expected",
    [(None, "light"), ("", "light"), ("light", "light"), ("dark", "dark"), ("sepia", "light")],
)
def test_mode_follows_the_browser_and_falls_back_to_light(monkeypatch, reported, expected):
    monkeypatch.setattr(theme, "_theme_type", lambda: reported)
    assert theme.mode() == expected
    assert theme.tokens() is (theme.DARK if expected == "dark" else theme.LIGHT)


def test_tokens_accepts_an_explicit_mode():
    assert theme.tokens("dark") is theme.DARK
    assert theme.tokens("light") is theme.LIGHT


def test_mode_is_light_outside_a_script_run():
    # plain import, no Streamlit script-run context: st.context.theme.type is None
    assert theme.mode() == "light"


@pytest.mark.parametrize("name", ["light", "dark"])
def test_config_toml_matches_tokens(name):
    tokens = theme.LIGHT if name == "light" else theme.DARK
    table = dict(_config()["theme"][name])
    sidebar = table.pop("sidebar")
    assert table == {opt: tokens[role] for opt, role in MAIN_ROLES.items()}
    assert sidebar == {opt: tokens[role] for opt, role in SIDEBAR_ROLES.items()}


def test_config_shared_theme_options():
    shared = {k: v for k, v in _config()["theme"].items() if not isinstance(v, dict)}
    assert shared == {
        "font": theme.FONT,
        "headingFont": theme.FONT,
        "baseRadius": "0px",
        "buttonRadius": "0px",
        "showSidebarBorder": True,
    }


def test_config_has_only_light_and_dark_tables():
    # the old single-mode [theme.sidebar] table and `base` must be gone
    tables = {k for k, v in _config()["theme"].items() if isinstance(v, dict)}
    assert tables == {"light", "dark"}
