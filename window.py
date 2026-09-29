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

import atexit
import subprocess
import sys
import time
import urllib.request

import webview

PORT = 8787
URL = f"http://localhost:{PORT}"

_backend: subprocess.Popen | None = None


def backend_up() -> bool:
    try:
        urllib.request.urlopen(f"{URL}/api/dayfile", timeout=2)
        return True
    except Exception:
        return False


def stop_backend() -> None:
    """Shut the server down with the window.

    Without this the uvicorn process outlived every quit and was reparented to
    launchd, and the reuse check below then found it still answering and kept
    it. The visible symptom was that quitting and reopening the app never
    picked up new code, because the server had been running since whenever it
    was first started.
    """
    global _backend
    if _backend is None or _backend.poll() is not None:
        return
    _backend.terminate()
    try:
        _backend.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _backend.kill()
    _backend = None


def start_backend() -> None:
    global _backend
    # A server this window did not start is left alone: it is someone running
    # uvicorn by hand, and killing it would pull the rug out from under them.
    # Anything this window starts, this window also stops.
    if backend_up():
        print(f"reusing the server already on {PORT}. If it is stale, stop it "
              f"first: kill $(lsof -ti:{PORT})", file=sys.stderr)
        return
    _backend = subprocess.Popen(
        [".venv/bin/uvicorn", "app.main:app", "--port", str(PORT), "--log-level", "warning"],
        stdout=open("server.log", "a"), stderr=subprocess.STDOUT,
    )
    atexit.register(stop_backend)
    for _ in range(40):
        if backend_up():
            return
        time.sleep(0.5)
    print("backend did not come up; see server.log", file=sys.stderr)
    stop_backend()
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
    try:
        webview.start()
    finally:
        stop_backend()
