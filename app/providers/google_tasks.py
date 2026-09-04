"""Google Tasks and Google Calendar, over the gws CLI.

Moved here from state.py unchanged. The subprocess helper, the two date
conversions, and the picks integration are all the originals: this file is a
relocation behind the provider seam, not a rewrite.
"""

import json
import subprocess
from datetime import datetime, timedelta


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


def _tz():
    from .. import state

    return state.tz()


def _day_starts_at() -> int:
    from .. import state

    return state.day_starts_at()


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
        local = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(_tz())
    except ValueError:
        return value[:10]
    if local.hour < _day_starts_at():
        local -= timedelta(days=1)
    return local.strftime("%Y-%m-%d")


class GoogleTasksProvider:
    name = "google"

    def __init__(self, tasklist: str = ""):
        self.tasklist = tasklist

    def check(self) -> tuple[bool, str]:
        try:
            _gws(["tasks", "tasklists", "list"])
        except Exception:
            return False, "the gws CLI is not installed or not authenticated"
        return True, "gws is authenticated"

    def list_tasks(self) -> dict:
        data = _gws([
            "tasks", "tasks", "list",
            "--params", json.dumps({
                "tasklist": self.tasklist,
                "showCompleted": True,
                "showHidden": True,
                "maxResults": 100,
            }),
        ])
        from .. import picks, state

        today_str = state.working_day()
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

    def complete(self, task_id: str) -> dict:
        return _gws([
            "tasks", "tasks", "patch",
            "--params", json.dumps({"tasklist": self.tasklist, "task": task_id}),
            "--json", json.dumps({"status": "completed"}),
        ])

    def uncomplete(self, task_id: str) -> dict:
        """Reopen a task. Only `status` goes in the body: sending a null
        `completed` alongside it makes the API reject the whole patch silently."""
        return _gws([
            "tasks", "tasks", "patch",
            "--params", json.dumps({"tasklist": self.tasklist, "task": task_id}),
            "--json", json.dumps({"status": "needsAction"}),
        ])

    def create(self, title: str, notes: str = "", due: str | None = None) -> dict:
        body: dict = {"title": title}
        if notes:
            body["notes"] = notes
        if due:
            body["due"] = f"{due}T00:00:00.000Z"
        return _gws([
            "tasks", "tasks", "insert",
            "--params", json.dumps({"tasklist": self.tasklist}),
            "--json", json.dumps(body),
        ])


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


class GoogleCalendar:
    name = "google"

    def check(self) -> tuple[bool, str]:
        try:
            _gws(["tasks", "tasklists", "list"])
        except Exception:
            return False, "the gws CLI is not installed or not authenticated"
        return True, "gws is authenticated"

    def today(self) -> dict:
        from .. import state

        now = state.today()
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
