"""Every dashboard page renders from the committed data/ snapshot, offline.

AppTest cannot switch between st.navigation pages that are functions
(switch_page only takes file paths), so each page function is called
directly through AppTest.from_function; one more test runs the real entry
point, which renders the default (national) page through st.navigation.
"""

import ast
import re
import socket
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parent.parent / "dashboard" / "app.py"
PAGES = ["national_page", "states_page", "revisions_page"]


_REAL_GETADDRINFO = socket.getaddrinfo
_LOCAL_HOSTS = (None, "localhost", "127.0.0.1", "::1")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    # Every outside connection (boto3/S3, urllib, requests) resolves a host
    # name first, so refusing non-local lookups blocks the network. Patching
    # socket.connect instead would break asyncio's local self-pipe on Windows,
    # which AppTest needs.
    def guarded_getaddrinfo(host, *args, **kwargs):
        if host not in _LOCAL_HOSTS:
            raise OSError(f"network access attempted during a smoke test: {host}")
        return _REAL_GETADDRINFO(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)


def _render(page_name: str) -> None:
    # runs inside AppTest: only names imported here are available
    import app

    app.apply_theme()
    getattr(app, page_name)()


def _run_page(page_name: str) -> AppTest:
    at = AppTest.from_function(_render, args=(page_name,), default_timeout=60)
    at.run()
    return at


@pytest.mark.parametrize("page_name", PAGES)
def test_page_renders_without_exceptions(page_name):
    at = _run_page(page_name)
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.markdown) > 0


def test_entry_point_renders_the_default_page():
    at = AppTest.from_file(str(APP), default_timeout=60)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.markdown) > 0


PAGE_TITLES = {
    "national_page": "National overview",
    "states_page": "State by state",
    "revisions_page": "Data revisions",
}


def _html(at: AppTest) -> str:
    return "\n".join(m.value for m in at.markdown)


@pytest.mark.parametrize("page_name, title", list(PAGE_TITLES.items()))
def test_page_has_the_civic_layout(page_name, title):
    at = _run_page(page_name)
    assert not at.exception, [e.value for e in at.exception]
    html = _html(at)
    assert '<header class="civic-masthead">US Economic Indicators</header>' in html
    assert f'aria-current="page">{title}</span>' in html
    assert f'role="heading" aria-level="1">{title}</div>' in html
    assert 'class="civic-tiles"' in html
    assert 'class="civic-footer"' in html
    assert len(at.metric) == 0  # tiles are HTML now, not st.metric
    for old in ("hero-title", "section-label", "tile-asof"):
        assert old not in html


def test_national_page_has_one_tile_per_indicator_and_the_banner():
    html = _html(_run_page("national_page"))
    assert html.count('<div class="civic-tile" role="listitem">') == 8
    assert 'class="civic-banner"' in html
    assert 'class="civic-brief"' in html
    assert "about 43% of flagged months turning out to be false alarms" in html


def _page_config_kwargs() -> dict:
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "set_page_config":
            return {kw.arg: ast.literal_eval(kw.value) for kw in node.keywords}
    raise AssertionError("no st.set_page_config call in app.py")


def test_sidebar_width_is_set_natively():
    # replaces the old 350px CSS rule; int widths need Streamlit >= 1.53
    assert _page_config_kwargs()["initial_sidebar_state"] == 350


def test_streamlit_floor_supports_the_sidebar_width():
    requirements = (APP.parent.parent / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"^streamlit>=1\.53,<2$", requirements, re.MULTILINE)


def test_pages_render_inside_the_civic_container():
    source = APP.read_text(encoding="utf-8")
    assert source.count("st.container(key=ui.PAGE_CONTAINER_KEY)") == 3
