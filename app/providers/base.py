"""What a provider has to offer.

These protocols write down the shape state.tasks() and mail.waiting() already
returned, so the existing callers never learn which backend answered.
"""

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
