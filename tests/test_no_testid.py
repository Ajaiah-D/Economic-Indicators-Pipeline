from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent.parent / "dashboard"
FORBIDDEN = "data-" + "testid"  # split so this file does not match itself


def test_no_streamlit_test_ids_anywhere_in_dashboard_code():
    offenders = [p.name for p in DASHBOARD.glob("*.py") if FORBIDDEN in p.read_text(encoding="utf-8")]
    assert offenders == []


def test_old_class_hooks_are_gone():
    source = (DASHBOARD / "app.py").read_text(encoding="utf-8")
    for old in ("inject_css", "statcard_", "hero-title", "section-label", "tile-asof", "stColumn"):
        assert old not in source, old
