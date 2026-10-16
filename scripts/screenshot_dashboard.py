"""
Screenshot every dashboard page in light and dark mode for visual review.

Needs a Python with Playwright + Chromium (on the author's machine:
C:\\Python314\\python). The Streamlit server runs from the repo's own
.venv, so the two environments stay separate:

    C:\\Python314\\python scripts/screenshot_dashboard.py [--out DIR] [--port N]

Dark mode comes from Playwright's color_scheme emulation. config.toml
defines [theme.light] and [theme.dark], and a fresh browser has no saved
choice, so Streamlit follows the (emulated) OS setting. Each shot is checked
against the painted page colour so a wrong-mode shot fails loudly.
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
VENV_PY = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
# shot name -> (URL path, H1). The default page lives at "/": visiting
# /national shows a "Page not found" dialog before falling back to it.
PAGES = {
    "national": ("", "National overview"),
    "states": ("states", "State by state"),
    "revisions": ("revisions", "Data revisions"),
}
# theme.LIGHT["PAGE"] / theme.DARK["PAGE"] as the browser reports them
PAGE_BACKGROUND = {"light": "rgb(255, 255, 255)", "dark": "rgb(21, 27, 34)"}
DESKTOP = {"width": 1200, "height": 750}
PHONE = {"width": 390, "height": 844}


def wait_for_server(base: str, server: subprocess.Popen, timeout: float = 90) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if server.poll() is not None:
            raise SystemExit(f"Streamlit server exited early (code {server.returncode}) before answering at {base}")
        try:
            with urllib.request.urlopen(f"{base}/_stcore/health", timeout=2) as resp:
                if resp.status == 200:
                    return
        except OSError:
            pass
        time.sleep(1)
    raise SystemExit(f"Streamlit did not answer at {base} within {timeout:.0f}s")


def open_page(page: Page, base: str, path: str, title: str) -> None:
    page.goto(f"{base}/{path}")
    page.get_by_role("heading", name=title, level=1).wait_for(timeout=60_000)
    page.wait_for_timeout(3000)  # let Plotly and the map iframe paint
    if page.get_by_text("Page not found").count():
        raise SystemExit(f"/{path}: Streamlit showed 'Page not found'")


def check_page(page: Page, scheme: str, label: str) -> None:
    background = page.evaluate("() => getComputedStyle(document.querySelector('.stApp')).backgroundColor")
    if background != PAGE_BACKGROUND[scheme]:
        raise SystemExit(f"{label}: expected {scheme} background {PAGE_BACKGROUND[scheme]}, got {background}")
    if page.locator(".st-key-civic_page").count() != 1:
        raise SystemExit(f"{label}: page container .st-key-civic_page not found")


def shoot(page: Page, out: Path, name: str, viewport: dict) -> None:
    page.screenshot(path=str(out / f"{name}.png"))
    # the page scrolls inside Streamlit's own container, so grow the viewport
    # to the content's height instead of using full_page=True
    height = page.evaluate(
        "() => { const r = document.querySelector('.st-key-civic_page').getBoundingClientRect();"
        " return r.top + r.height; }"
    )
    page.set_viewport_size({"width": viewport["width"], "height": min(int(height) + 120, 8000)})
    page.wait_for_timeout(1500)
    page.screenshot(path=str(out / f"{name}-full.png"))
    page.set_viewport_size(viewport)
    page.wait_for_timeout(500)
    print(f"  {name}.png, {name}-full.png")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / "eip-screenshots")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    base = f"http://localhost:{args.port}"

    try:
        socket.create_connection(("localhost", args.port), 1).close()
    except OSError:
        pass
    else:
        raise SystemExit(f"Port {args.port} is already in use; stop that server or pass --port")

    server = subprocess.Popen(
        [str(VENV_PY), "-m", "streamlit", "run", "dashboard/app.py",
         "--server.headless", "true", "--server.port", str(args.port),
         "--browser.gatherUsageStats", "false"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    try:
        wait_for_server(base, server)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for scheme in ("light", "dark"):
                ctx = browser.new_context(viewport=DESKTOP, device_scale_factor=2, color_scheme=scheme)
                page = ctx.new_page()
                for name, (path, title) in PAGES.items():
                    open_page(page, base, path, title)
                    check_page(page, scheme, f"{name}-{scheme}")
                    shoot(page, out, f"{name}-{scheme}", DESKTOP)
                if scheme == "light":
                    # the breadcrumb's Home link leads back to the national page
                    open_page(page, base, *PAGES["states"])
                    page.get_by_role("link", name="Home", exact=True).click()
                    page.get_by_role("heading", name=PAGES["national"][1], level=1).wait_for(timeout=60_000)
                    print("  breadcrumb Home link: OK")
                    # GOV.UK focus ring on the Home link
                    page.get_by_role("link", name="Home", exact=True).focus()
                    page.wait_for_timeout(300)
                    page.screenshot(path=str(out / "focus-ring-light.png"),
                                    clip={"x": 0, "y": 0, "width": DESKTOP["width"], "height": 320})
                    print("  focus-ring-light.png")
                ctx.close()

            ctx = browser.new_context(viewport=PHONE, device_scale_factor=2, color_scheme="light")
            page = ctx.new_page()
            open_page(page, base, *PAGES["national"])
            check_page(page, "light", "national-light-phone")
            overflow = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
            if overflow > 0:
                print(f"  WARNING: phone layout scrolls sideways by {overflow}px")
            shoot(page, out, "national-light-phone", PHONE)
            ctx.close()
            browser.close()
    finally:
        if sys.platform == "win32":
            # the venv launcher's child process otherwise survives and keeps the port
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(server.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
    print(f"Screenshots in {out}")


if __name__ == "__main__":
    main()
