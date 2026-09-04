"""What a provider has to offer.

These protocols write down the shape state.tasks() and mail.waiting() already
returned, so the existing callers never learn which backend answered.
"""

from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

BUCKETS = ("picked", "due_today", "overdue", "undated", "done_today")


def EMPTY_TASKS() -> dict:
    return {b: [] for b in BUCKETS}


def task_row(id: str, title: str, due: str = "", notes: str = "") -> dict:
    """One task, in the shape the dashboard expects."""
    return {"id": id, "title": title, "due": due, "notes": notes}


@runtime_checkable
class TaskProvider(Protocol):
    name: str

    def check(self) -> tuple[bool, str]:
        """Is this usable right now, and if not, what would fix it."""

    def list_tasks(self) -> dict:
        """Every bucket in BUCKETS, each a list of task_row dicts."""

    def complete(self, task_id: str) -> dict: ...

    def uncomplete(self, task_id: str) -> dict: ...

    def create(self, title: str, notes: str = "", due: str | None = None) -> dict:
        """Returns at least an id."""


@runtime_checkable
class MailProvider(Protocol):
    name: str

    def check(self) -> tuple[bool, str]: ...

    def waiting(self, limit: int = 40) -> list[dict]:
        """Threads where the reply is yours to write."""


def completed_working_day(value: str) -> str:
    """A UTC completion instant as the local working day it belongs to.

    Two corrections happen here. Without the timezone conversion, anything
    finished after 8pm Eastern lands on tomorrow's UTC date and drops off the
    list. Without the day boundary, work finished at 00:30 starts a new day.

    Every provider that reports completions needs this, so it lives here
    rather than in one of them. A provider that slices the raw string instead
    reintroduces the bug this project already fixed once.
    """
    from .. import state

    if not value:
        return ""
    try:
        local = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(state.tz())
    except ValueError:
        return value[:10]
    if local.hour < state.day_starts_at():
        local -= timedelta(days=1)
    return local.strftime("%Y-%m-%d")
