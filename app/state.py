"""Google Tasks and Calendar reads, plus day-file access."""

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# Your Google Tasks list. Find it with: gws tasks tasklists list
TASKLIST = os.environ.get("HERD_TASKLIST", "")
TZ = ZoneInfo("America/Indiana/Indianapolis")
DAILY_DIR = Path.home() / "tools-and-projects" / "rosie" / "daily"


def _gws(args: list[str]) -> dict:
    proc = subprocess.run(
        ["gws", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[:300] or "gws failed")
    return json.loads(proc.stdout)


DAY_STARTS_AT = 6  # local hour


def today() -> datetime:
    return datetime.now(TZ)


def working_day() -> str:
    """The day the pile belongs to, on a 6am boundary rather than midnight.

    Work finished at 00:30 belongs to the night before, not to a fresh day
    nobody has started yet.
    """
    now = datetime.now(TZ)
    if now.hour < DAY_STARTS_AT:
        now -= timedelta(days=1)
    return now.strftime("%Y-%m-%d")


def _local_date(value: str) -> str:
    """Due dates are UTC-midnight markers, so their date part IS the intended day."""
    return value[:10] if value else ""


def _completed_date(value: str) -> str:
    """Completion is a real UTC instant, converted to the local working day.

    Two corrections happen here. Without the timezone conversion, anything
    finished after 8pm ET lands on tomorrow's UTC date and drops off the list.
    Without the 6am boundary, work finished at 00:30 starts a new day.
    """
    if not value:
        return ""
    try:
        local = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(TZ)
    except ValueError:
        return value[:10]
    if local.hour < DAY_STARTS_AT:
        local -= timedelta(days=1)
    return local.strftime("%Y-%m-%d")


def tasks() -> dict:
    data = _gws([
        "tasks", "tasks", "list",
        "--params", json.dumps({
            "tasklist": TASKLIST,
            "showCompleted": True,
            "showHidden": True,
            "maxResults": 100,
        }),
    ])
    from . import picks  # local, since picks imports state for the day boundary

    today_str = working_day()
    starred = picks.today()

    picked, due_today, overdue, undated, done_today = [], [], [], [], []
    for item in data.get("items", []):
        row = {
            "id": item.get("id"),
            "title": (item.get("title") or "").strip(),
            "due": _local_date(item.get("due", "")),
            "notes": item.get("notes", ""),
        }
        if not row["title"]:
            continue
        if item.get("status") == "completed":
            if _completed_date(item.get("completed", "")) == today_str:
                row["completed"] = item.get("completed", "")
                done_today.append(row)
            continue
        # A pick lifts the task into its own pile rather than copying it, so
        # nothing shows up twice and "due today" keeps meaning a real deadline.
        if row["id"] in starred:
            row["picked"] = True
            picked.append(row)
        elif not row["due"]:
            undated.append(row)
        elif row["due"] == today_str:
            due_today.append(row)
        elif row["due"] < today_str:
            overdue.append(row)

    return {
        "picked": picked,
        "due_today": due_today,
        "overdue": overdue,
        "undated": undated,
        "done_today": done_today,
    }


def calendar() -> dict:
    now = today()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    data = _gws([
        "calendar", "events", "list",
        "--params", json.dumps({
            "calendarId": "primary",
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "singleEvents": True,
            "orderBy": "startTime",
        }),
    ])

    events = []
    for item in data.get("items", []):
        s = item.get("start", {})
        e = item.get("end", {})
        start_dt = s.get("dateTime")
        if not start_dt:
            continue  # all-day events are location markers, not commitments
        events.append({
            "id": item.get("id"),
            "summary": item.get("summary", "(no title)"),
            "start": start_dt,
            "end": e.get("dateTime", ""),
            "type": item.get("eventType", "default"),
        })

    now_iso = now.isoformat()
    current = None
    for ev in events:
        ev["past"] = bool(ev["end"]) and ev["end"] < now_iso
        ev["live"] = ev["start"] <= now_iso < (ev["end"] or ev["start"])
        if ev["live"] and current is None:
            current = ev

    return {"events": events, "now": current, "collisions": _collisions(events)}


HOLD_HOURS = 3


def _is_hold(ev: dict) -> bool:
    """A long self-booked block is protected time, not a commitment.

    Everything scheduled inside a "do not book" window overlaps it by design,
    so counting those as collisions buries the real ones.
    """
    if not (ev["start"] and ev["end"]):
        return False
    try:
        hours = (datetime.fromisoformat(ev["end"]) - datetime.fromisoformat(ev["start"]))
    except ValueError:
        return False
    return hours >= timedelta(hours=HOLD_HOURS)


def _collisions(events: list[dict]) -> list[dict]:
    """Overlapping commitments, and task blocks buried under meetings."""
    real = sorted(
        (e for e in events if not _is_hold(e) and e["start"] and e["end"]),
        key=lambda e: e["start"],
    )
    out = []
    for i, a in enumerate(real):
        for b in real[i + 1:]:
            if b["start"] >= a["end"]:
                break  # sorted, so nothing later can overlap a either
            out.append({
                "a": a["summary"].strip(), "b": b["summary"].strip(),
                "at": b["start"][11:16],
                "task_block": a["type"] == "focusTime" or b["type"] == "focusTime",
            })
    return out


def day_file_path(date: str | None = None) -> Path:
    return DAILY_DIR / f"{date or working_day()}.md"


def day_file() -> str:
    path = day_file_path()
    return path.read_text() if path.exists() else ""


def append_done(text: str) -> None:
    """Add a line to the day file's On the list section as already done."""
    path = day_file_path()
    stamp = today().strftime("%H:%M")
    line = f"- [x] {text} ({stamp})\n"
    if not path.exists():
        day = datetime.strptime(working_day(), "%Y-%m-%d")
        path.write_text(
            f"# {day.strftime('%Y-%m-%d, %A')}\n\n## On the list\n{line}\n"
            "## Decisions\n\n## Open threads\n\n## Notes\n"
        )
        return
    body = path.read_text()
    marker = "## Decisions"
    if marker in body:
        head, _, tail = body.partition(marker)
        path.write_text(f"{head.rstrip()}\n{line}\n{marker}{tail}")
    else:
        path.write_text(body.rstrip() + "\n" + line)


def append_note(text: str, about: str = "") -> None:
    """Drop a note into the day file for Claude Code to pick up.

    Notes land in their own "## For Claude" section rather than in Notes, so
    the ones written at the dashboard asking for something are separable from
    the ones Claude wrote down as reference.
    """
    path = day_file_path()
    stamp = today().strftime("%H:%M")
    line = f"- [ ] {stamp}" + (f" **{about}** - " if about else " ") + text + "\n"
    section = "## For Claude"

    if not path.exists():
        day = datetime.strptime(working_day(), "%Y-%m-%d")
        path.write_text(
            f"# {day.strftime('%Y-%m-%d, %A')}\n\n## On the list\n\n"
            f"{section}\n{line}\n## Decisions\n\n## Open threads\n\n## Notes\n"
        )
        return

    body = path.read_text()
    if section in body:
        head, _, tail = body.partition(section)
        rest = tail.split("\n## ", 1)
        entries = rest[0].rstrip("\n")
        remainder = ("\n## " + rest[1]) if len(rest) > 1 else ""
        path.write_text(f"{head}{section}{entries}\n{line}{remainder}")
    elif "## Decisions" in body:
        head, _, tail = body.partition("## Decisions")
        path.write_text(f"{head.rstrip()}\n\n{section}\n{line}\n## Decisions{tail}")
    else:
        path.write_text(body.rstrip() + f"\n\n{section}\n{line}")


def uncomplete_task(task_id: str) -> dict:
    """Reopen a task. Only `status` goes in the body: sending a null
    `completed` alongside it makes the API reject the whole patch silently."""
    return _gws([
        "tasks", "tasks", "patch",
        "--params", json.dumps({"tasklist": TASKLIST, "task": task_id}),
        "--json", json.dumps({"status": "needsAction"}),
    ])


def complete_task(task_id: str) -> dict:
    return _gws([
        "tasks", "tasks", "patch",
        "--params", json.dumps({"tasklist": TASKLIST, "task": task_id}),
        "--json", json.dumps({"status": "completed"}),
    ])


def create_task(title: str, notes: str = "", due: str | None = None) -> dict:
    body: dict = {"title": title}
    if notes:
        body["notes"] = notes
    if due:
        body["due"] = f"{due}T00:00:00.000Z"
    return _gws([
        "tasks", "tasks", "insert",
        "--params", json.dumps({"tasklist": TASKLIST}),
        "--json", json.dumps(body),
    ])
