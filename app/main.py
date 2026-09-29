import asyncio
import json
import subprocess
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import (agent, cats, docs, mail, picks, rollover, runs, setup, state,
               sweep, watch)

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


@app.post("/api/mail/archive")
async def archive_mail(body: dict):
    """Archive a thread so it stops showing up in the waiting list."""
    thread_id = (body.get("id") or "").strip()
    if not thread_id:
        return {"ok": False, "error": "missing thread id"}
    return await asyncio.to_thread(mail.archive, thread_id)


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


@app.get("/api/runs")
async def get_runs(limit: int = 50):
    """The sweep run log: when each ran, what it cost, and on which models.

    Separate from /api/sweep, which is only ever the most recent run.
    """
    rows = await asyncio.to_thread(runs.read, limit)
    return {"runs": rows, "summary": await asyncio.to_thread(runs.summary, rows)}


@app.get("/api/sweep")
async def sweep_status():
    """What the last sweep found, and whether another one is allowed yet."""
    prev = sweep.last()
    return {
        "clock": prev.get("clock", ""),
        "day": prev.get("day", ""),
        "logged": prev.get("logged", 0),
        "summary": prev.get("summary", ""),
        "cooling": sweep.cooling(),
    }


# One sweep at a time. Two overlapping runs would both find the same evidence
# and log it twice, since neither can see what the other is part way through
# writing.
_sweeping = asyncio.Lock()


def _bound_port(request: Request) -> int:
    """The port this server is actually listening on.

    The agent is a separate process, so it needs a port that reaches the app
    rather than whatever the browser happened to type. The server socket is
    the authority; the request URL is the fallback for the case where the
    scope carries no socket, and 8787 is the documented default behind that.
    """
    sock = request.scope.get("server")
    if sock and sock[1]:
        return int(sock[1])
    return request.url.port or 8787


@app.post("/api/sweep")
async def run_sweep(request: Request, force: bool = False,
                    trigger: str = "button"):
    """Sweep for finished work and log whatever cleared the strong-evidence bar.

    Streams as server-sent events rather than returning at the end, because a
    run takes long enough that a silent button looks hung.
    """
    if _sweeping.locked():
        return JSONResponse({"ok": False, "error": "a sweep is already running"},
                            status_code=409)
    left = sweep.cooling()
    if left and not force:
        return JSONResponse(
            {"ok": False, "error": f"swept {left // 60}m ago", "cooling": left},
            status_code=429)

    # The port the agent is told to POST to. request.url.port is the port the
    # browser used, which is the same thing in the normal case and the wrong
    # thing behind anything that rewrites the host, so prefer the socket the
    # server is actually bound to.
    port = _bound_port(request)

    async def stream():
        async with _sweeping:
            agent.reset()
            lines: list[str] = []
            spend: dict = {}
            # Sync first here too, or a day-file line written before the sweep
            # but not yet synced gets counted as something this run found.
            await asyncio.to_thread(cats.sync_day_file)
            before = len((await asyncio.to_thread(cats.herd)).get("today", []))
            try:
                async for event in agent.ask(
                    sweep.prompt(port), sweep.allowed(), sweep.agents(),
                    sweep.MODEL,
                ):
                    if event.get("type") == "text":
                        lines.append(event["text"])
                    elif event.get("type") == "usage":
                        # Arrives once, on the CLI's final result event, and
                        # exists nowhere else. Miss it and the run cannot be
                        # priced afterwards.
                        spend = event
                    yield f"data: {json.dumps(event)}\n\n"
            except Exception as exc:
                # Record the failure too. A crashed run that logs nothing is
                # exactly what a gap in the log should be traceable to, and
                # it has usually already spent tokens by the time it dies.
                await asyncio.to_thread(
                    runs.record,
                    trigger=trigger,
                    logged=0,
                    cost_usd=spend.get("cost_usd"),
                    duration_ms=spend.get("duration_ms"),
                    models=spend.get("models"),
                    error=str(exc),
                )
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)[:300]})}\n\n"
                return

            # The last text block is the answer. Everything before it is the
            # agent narrating its way through the sweep ("let me check X"),
            # which joined together ran to thousands of characters of
            # mid-sentence noise and made the tooltip unreadable.
            summary = (lines[-1] if lines else "").strip()
            # Sync before counting. /api/done writes the day file and stops
            # there, and the cat is awarded by sync_day_file on the next state
            # read. Counting straight after the run therefore saw seven fresh
            # lines in the file and zero new cats, and reported "0 logged" on a
            # sweep that had just found seven real completions.
            await asyncio.to_thread(cats.sync_day_file)
            # Count from the herd rather than from the reply. Counting reply
            # lines looked simpler and was wrong: a run that logged nothing and
            # explained why at length reported "13 logged", because thirteen is
            # how many lines the explanation ran to. The herd is the record the
            # count is actually about.
            after = await asyncio.to_thread(cats.herd)
            logged = max(0, len(after.get("today", [])) - before)
            await asyncio.to_thread(sweep.record, logged, summary)
            row = await asyncio.to_thread(
                runs.record,
                trigger=trigger,
                logged=logged,
                cost_usd=spend.get("cost_usd"),
                duration_ms=spend.get("duration_ms"),
                models=spend.get("models"),
            )
            yield f"data: {json.dumps({'type': 'swept', 'logged': logged, 'summary': summary, 'run': row})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store",
                                      "X-Accel-Buffering": "no"})


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
