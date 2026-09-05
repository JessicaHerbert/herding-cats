import asyncio
import subprocess
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import cats, docs, mail, picks, rollover, setup, state, watch

if setup.needed():
    raise SystemExit(
        "No config yet. Run:  .venv/bin/python -m app.setup"
    )

app = FastAPI(title="herding cats")
WEB = Path(__file__).parent.parent / "web"


@app.get("/api/state")
async def get_state():
    # Make sure the day exists before anything reads it, so the watchlist
    # carries over instead of starting empty every morning.
    out: dict = {"rollover": await asyncio.to_thread(rollover.ensure_today)}
    for name, fn in (("tasks", state.tasks), ("calendar", state.calendar)):
        try:
            out[name] = await asyncio.to_thread(fn)
        except Exception as exc:
            out[name] = {"error": str(exc)[:200]}
    out["date"] = state.today().strftime("%A, %B %-d")
    out["time"] = state.today().strftime("%H:%M")
    await asyncio.to_thread(cats.sync_day_file)
    # Completions made outside the dashboard still earn their cat.
    if isinstance(out.get("tasks"), dict):
        await asyncio.to_thread(cats.sync_completed, out["tasks"].get("done_today", []))
    out["herd"] = await asyncio.to_thread(cats.herd)
    out["watching"] = await asyncio.to_thread(watch.watching)
    return out


@app.get("/api/history")
async def get_history():
    return await asyncio.to_thread(cats.history)


@app.get("/api/docs")
async def get_docs(days: int = 7):
    return await asyncio.to_thread(docs.touched, days)


@app.get("/api/mail")
async def get_mail():
    """Separate from /api/state: this shells out per thread, so it belongs on
    the slow timer rather than the 60-second one."""
    from . import providers

    provider = providers.mail()
    if provider is None:
        return {"waiting": []}
    try:
        return {"waiting": await asyncio.to_thread(mail.waiting)}
    except Exception as exc:
        return {"waiting": [], "error": str(exc)[:200]}


@app.post("/api/open")
async def open_external(body: dict):
    """Hand a URL or a local file to the system default handler.

    The app window is signed into nothing, so a plain link would open in a
    browser with no session. `open` respects the real system default for both
    web links and files.
    """
    target = (body.get("url") or "").strip()

    if target.startswith(("http://", "https://")):
        pass
    elif target.startswith("/"):
        path = Path(target).resolve()
        # Only open things the dashboard could legitimately be showing, so a
        # crafted request cannot make the app open arbitrary files.
        allowed = (Path.home() / "tools-and-projects", Path.home() / "canvas-stacks",
                   Path.home() / ".claude", Path.home() / "Desktop",
                   Path.home() / "Documents", Path.home() / "marketing")
        if not path.exists() or not any(path.is_relative_to(a) for a in allowed):
            return JSONResponse({"ok": False, "error": "not an openable path"},
                                status_code=400)
        target = str(path)
    else:
        return JSONResponse({"ok": False, "error": "unsupported target"},
                            status_code=400)

    await asyncio.to_thread(subprocess.run, ["open", target], check=False, timeout=10)
    return {"ok": True}


@app.get("/api/dayfile")
async def get_dayfile():
    return {"markdown": await asyncio.to_thread(state.day_file)}


@app.post("/api/task/{task_id}/complete")
async def complete(task_id: str, body: dict | None = None):
    try:
        await asyncio.to_thread(state.complete_task, task_id)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)[:200]}, status_code=500)
    title = (body or {}).get("title", "a task")
    earned = await asyncio.to_thread(cats.earn, title)
    # The cat goes in herd.json, but the day file is the record that outlives
    # the session, and only /api/done was writing to it. Seven completions
    # logged here on 2026-09-04 reached the herd and never the file, which left
    # the day file hours behind and a later session reading it drew the wrong
    # window. Skip duplicates, since the cat was not awarded either.
    if earned.get("cat"):
        await asyncio.to_thread(state.append_done, title)
    return {"ok": True, "earned": earned}


@app.post("/api/task/{task_id}/uncomplete")
async def uncomplete(task_id: str, body: dict | None = None):
    """Undo an accidental completion: reopen the task and take the cat back."""
    # A cat earned from the day file has no task behind it, so "none" means
    # take the cat back and leave Google Tasks alone.
    if task_id != "none":
        try:
            await asyncio.to_thread(state.uncomplete_task, task_id)
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)[:200]}, status_code=500)
    title = (body or {}).get("title", "")
    given_back = await asyncio.to_thread(cats.unearn, title) if title else {}
    return {"ok": True, "herd": given_back}


@app.post("/api/task/{task_id}/pick")
async def pick(task_id: str):
    """Star a task for today, or unstar it."""
    return {"ok": True, "picked": await asyncio.to_thread(picks.toggle, task_id)}


@app.post("/api/note")
async def add_note(body: dict):
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"ok": False, "error": "text required"}, status_code=400)
    await asyncio.to_thread(state.append_note, text, (body.get("about") or "").strip())
    return {"ok": True}


@app.post("/api/task")
async def add_task(body: dict):
    title = (body.get("title") or "").strip()
    if not title:
        return JSONResponse({"ok": False, "error": "title required"}, status_code=400)
    try:
        created = await asyncio.to_thread(
            state.create_task, title, body.get("notes", ""), body.get("due")
        )
        return {"ok": True, "id": created.get("id")}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)[:200]}, status_code=500)


@app.post("/api/done")
async def log_done(body: dict):
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"ok": False, "error": "text required"}, status_code=400)
    await asyncio.to_thread(state.append_done, text)
    return {"ok": True}


@app.websocket("/ws")
async def retired_ws(ws: WebSocket):
    """Chat moved to Claude Code. A cached page still dialing this endpoint
    would otherwise fall through to StaticFiles and crash on a non-http scope."""
    await ws.close(code=1000)


@app.middleware("http")
async def no_cache(request, call_next):
    """A local tool changes constantly; a stale cached app.js is never wanted."""
    response = await call_next(request)
    if request.url.path.endswith((".js", ".css", ".html")) or request.url.path == "/":
        response.headers["Cache-Control"] = "no-store, must-revalidate"
    return response


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
