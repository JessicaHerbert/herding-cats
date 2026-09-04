"""Every provider must map a UTC completion to the same working day.

The Todoist provider sliced the raw UTC string with [:10] and compared it to
a local, boundary-shifted date. Evening completions and post-midnight ones
both dropped out of done_today, which is the bug this project already fixed
once in the rollover.
"""

import pytest

from app import config
from app.providers import base, google_tasks


@pytest.fixture
def eastern(tmp_home):
    (tmp_home / "config.toml").write_text(
        '[general]\ntimezone = "America/New_York"\nday_starts_at = 6\n'
        '[tasks]\nprovider = "localfile"\npath = "/tmp/t.md"\n'
        '[mail]\nprovider = "none"\n'
    )
    config.reload()


def test_an_evening_completion_stays_on_its_own_day(eastern):
    """23:00 Eastern is already tomorrow in UTC. Slicing the raw string
    would push it to the next day and drop it off today's list."""
    assert base.completed_working_day("2026-09-05T03:00:00Z") == "2026-09-04"


def test_a_post_midnight_completion_files_to_the_night_before(eastern):
    assert base.completed_working_day("2026-09-04T05:30:00Z") == "2026-09-03"


def test_a_daytime_completion_is_its_own_day(eastern):
    assert base.completed_working_day("2026-09-04T18:00:00Z") == "2026-09-04"


def test_empty_stays_empty(eastern):
    assert base.completed_working_day("") == ""


def test_google_uses_the_shared_helper(eastern):
    """google_tasks._completed_date delegates, so a missing import or a
    divergent copy shows up here rather than in production."""
    assert google_tasks._completed_date("2026-09-05T03:00:00Z") == "2026-09-04"


def test_todoist_uses_the_shared_helper(eastern, monkeypatch):
    from app.providers.todoist import TodoistProvider

    monkeypatch.setattr("app.providers.todoist._today", lambda: "2026-09-04")

    def fake(self, method, path, params=None, body=None):
        if path == "/tasks":
            return {"results": [], "next_cursor": None}
        return {
            "results": [
                {"id": "1", "content": "Late night thing", "description": "",
                 "due": None, "checked": True,
                 "completed_at": "2026-09-05T03:00:00Z"},
            ],
            "next_cursor": None,
        }

    monkeypatch.setattr(TodoistProvider, "_request", fake)
    out = TodoistProvider("t").list_tasks()
    assert [t["title"] for t in out["done_today"]] == ["Late night thing"]
