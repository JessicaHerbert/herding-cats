"""Tasks Jess picked for today.

Google Tasks has no "I want to do this today" field, and a due date is the
wrong tool for it: most of the backlog has no real deadline, and stamping one
on turns a choice into a fake commitment that then reads as overdue tomorrow.

So the picks live here, keyed by task id and scoped to a working day. Google
Tasks stays the source of truth for what the tasks ARE; this only records
which of them Jess pulled forward this morning.
"""

import json
from pathlib import Path

from . import paths, state


def _picks_file() -> Path:
    """Resolved per call, for the same reason as the herd file."""
    return paths.picks_file()


def _load() -> dict:
    if not _picks_file().exists():
        return {}
    try:
        return json.loads(_picks_file().read_text())
    except json.JSONDecodeError:
        return {}


def _save(data: dict) -> None:
    paths.ensure()
    _picks_file().write_text(json.dumps(data, indent=2) + "\n")


def today() -> set[str]:
    return set(_load().get(state.working_day(), []))


def toggle(task_id: str) -> bool:
    """Star or unstar a task for today. Returns whether it is now picked."""
    data = _load()
    day = state.working_day()
    ids = data.setdefault(day, [])

    if task_id in ids:
        ids.remove(task_id)
        picked = False
    else:
        ids.append(task_id)
        picked = True

    # Keep only the last couple of weeks, since a pick has no meaning once
    # its day has passed.
    for old in sorted(data)[:-14]:
        del data[old]

    _save(data)
    return picked
