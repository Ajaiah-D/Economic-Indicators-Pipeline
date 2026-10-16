"""Every dashboard page renders from the committed data/ snapshot, offline.

AppTest cannot switch between st.navigation pages that are functions
(switch_page only takes file paths), so each page function is called
directly through AppTest.from_function; one more test runs the real entry
point, which renders the default (national) page through st.navigation.
"""

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
