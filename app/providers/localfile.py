"""Tasks from a markdown file. No account, no network, no auth.

This is also the honesty test for the provider seam: with no server and no
assigned ids, anything Google-shaped that leaked into the interface would
show up here immediately.
"""

import hashlib
import re
from pathlib import Path

from . import base

LINE = re.compile(r"^\s*-\s*\[( |x|X)\]\s+(.*?)\s*$")
DUE = re.compile(r"\s*\(due (\d{4}-\d{2}-\d{2})\)\s*$")
DONE = re.compile(r"\s*\(done (\d{4}-\d{2}-\d{2})\)\s*$")

HEADER = "# Tasks\n\nOne per line. Add `(due YYYY-MM-DD)` to give one a date.\n\n"


def _today() -> str:
    from .. import state

    return state.working_day()


def _task_id(title: str) -> str:
    return hashlib.sha1(title.encode()).hexdigest()[:12]


class LocalFileProvider:
    name = "localfile"

    def __init__(self, path: str):
        self.path = Path(path).expanduser()

    def check(self) -> tuple[bool, str]:
        if not self.path.exists():
            return False, f"no task file at {self.path}"
        return True, f"reading {self.path}"

    def _lines(self) -> list[str]:
        if not self.path.exists():
            return []
        return self.path.read_text().splitlines()

    def _write(self, lines: list[str]) -> None:
        self.path.write_text("\n".join(lines) + "\n")

    def list_tasks(self) -> dict:
        out = base.EMPTY_TASKS()
        today = _today()

        for line in self._lines():
            m = LINE.match(line)
            if not m:
                continue
            checked = m.group(1).lower() == "x"
            body = m.group(2)

            done_on = ""
            due_on = ""
            if dm := DONE.search(body):
                done_on = dm.group(1)
                body = DONE.sub("", body)
            if um := DUE.search(body):
                due_on = um.group(1)
                body = DUE.sub("", body)

            title = body.strip()
            if not title:
                continue
            row = base.task_row(id=_task_id(title), title=title, due=due_on)

            if checked:
                if done_on == today:
                    row["completed"] = done_on
                    out["done_today"].append(row)
            elif not due_on:
                out["undated"].append(row)
            elif due_on == today:
                out["due_today"].append(row)
            elif due_on < today:
                out["overdue"].append(row)
        return out

    def _rewrite(self, task_id: str, to_done: bool) -> dict:
        lines = self._lines()
        for i, line in enumerate(lines):
            m = LINE.match(line)
            if not m:
                continue
            body = DONE.sub("", DUE.sub("", m.group(2))).strip()
            if _task_id(body) != task_id:
                continue

            rest = m.group(2)
            rest = DONE.sub("", rest).rstrip()
            if to_done:
                lines[i] = f"- [x] {rest} (done {_today()})"
            else:
                lines[i] = f"- [ ] {rest}"
            self._write(lines)
            return {"id": task_id}
        return {}

    def complete(self, task_id: str) -> dict:
        return self._rewrite(task_id, to_done=True)

    def uncomplete(self, task_id: str) -> dict:
        return self._rewrite(task_id, to_done=False)

    def create(self, title: str, notes: str = "", due: str | None = None) -> dict:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(HEADER)
        line = f"- [ ] {title}" + (f" (due {due})" if due else "")
        with self.path.open("a") as fh:
            fh.write(line + "\n")
        return {"id": _task_id(title)}
