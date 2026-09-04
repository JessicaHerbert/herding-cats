#!/usr/bin/env uv run
"""The app window: a native WKWebView rather than a browser.

Chrome was the placeholder while the web app got built. It opened a new window
on every launch, put the dashboard behind a browser chrome that could get lost,
and ran a whole second browser engine for one local page. WKWebView is already
in macOS, so this is a real app window with its own Dock icon and nothing else
running behind it.

External links still hand off to the real default browser through /api/open,
since this window is signed into nothing.
"""

import subprocess
import sys
import time
import urllib.request

import webview

PORT = 8787
URL = f"http://localhost:{PORT}"


def backend_up() -> bool:
    try:
        urllib.request.urlopen(f"{URL}/api/dayfile", timeout=2)
        return True
    except Exception:
        return False


def start_backend() -> None:
    if backend_up():
        return
    subprocess.Popen(
        [".venv/bin/uvicorn", "app.main:app", "--port", str(PORT), "--log-level", "warning"],
        stdout=open("server.log", "a"), stderr=subprocess.STDOUT,
    )
    for _ in range(40):
        if backend_up():
            return
        time.sleep(0.5)
    print("backend did not come up; see server.log", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    start_backend()
    webview.create_window(
        "herding cats",
        URL,
        width=1360,
        height=900,
        min_size=(900, 600),
    )
    webview.start()
