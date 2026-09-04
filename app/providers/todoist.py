"""Todoist, over the v1 REST API.

Two things differ from most examples. The /rest/v2/ API is retired and
answers 410, so everything here is /api/v1. And GET /tasks returns active
tasks only with no date filter, so anything finished comes from a separate
completed endpoint that requires an explicit window.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from . import base

BASE = "https://api.todoist.com/api/v1"


def _today() -> str:
    from .. import state

    return state.working_day()


class TodoistProvider:
    name = "todoist"

    def __init__(self, token: str):
        self.token = token

    def _request(self, method: str, path: str, params=None, body=None) -> dict:
        url = BASE + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} from Todoist {path}") from exc

    def check(self) -> tuple[bool, str]:
        try:
            self._request("GET", "/tasks", params={"limit": 1})
            return True, "token accepted"
        except Exception as exc:
            return False, str(exc)

    def _paged(self, path: str, params: dict) -> list[dict]:
        out: list[dict] = []
        cursor = None
        while True:
            page = dict(params)
            if cursor:
                page["cursor"] = cursor
            data = self._request("GET", path, params=page)
            out.extend(data.get("results", []))
            cursor = data.get("next_cursor")
            if not cursor:
                return out

    def _row(self, item: dict) -> dict:
        due = (item.get("due") or {}).get("date", "") or ""
        return base.task_row(
            id=str(item.get("id", "")),
            title=(item.get("content") or "").strip(),
            due=due[:10],
            notes=item.get("description") or "",
        )

    def list_tasks(self) -> dict:
        out = base.EMPTY_TASKS()
        today = _today()

        for item in self._paged("/tasks", {"limit": 200}):
            row = self._row(item)
            if not row["title"]:
                continue
            if not row["due"]:
                out["undated"].append(row)
            elif row["due"] == today:
                out["due_today"].append(row)
            elif row["due"] < today:
                out["overdue"].append(row)

        # Completed tasks are a different endpoint and the window is required.
        since = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=2)).strftime(
            "%Y-%m-%dT00:00:00"
        )
        until = (datetime.strptime(today, "%Y-%m-%d") + timedelta(days=1)).strftime(
            "%Y-%m-%dT00:00:00"
        )
        for item in self._paged(
            "/tasks/completed/by_completion_date",
            {"since": since, "until": until, "limit": 200},
        ):
            done_at = (item.get("completed_at") or "")[:10]
            if done_at != today:
                continue
            row = self._row(item)
            row["completed"] = item.get("completed_at", "")
            out["done_today"].append(row)
        return out

    def complete(self, task_id: str) -> dict:
        return self._request("POST", f"/tasks/{task_id}/close")

    def uncomplete(self, task_id: str) -> dict:
        return self._request("POST", f"/tasks/{task_id}/reopen")

    def create(self, title: str, notes: str = "", due: str | None = None) -> dict:
        body = {"content": title}
        if notes:
            body["description"] = notes
        if due:
            body["due_date"] = due
        return self._request("POST", "/tasks", body=body)
