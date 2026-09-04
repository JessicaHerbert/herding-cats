import json

import pytest

from app.providers import base
from app.providers.todoist import TodoistProvider


@pytest.fixture
def fake_api(monkeypatch):
    """Record calls and hand back canned Todoist payloads."""
    calls = []

    def fake_request(self, method, path, params=None, body=None):
        calls.append({"method": method, "path": path, "params": params, "body": body})
        if path == "/tasks":
            return {
                "results": [
                    {"id": "1", "content": "Water the plants", "description": "",
                     "due": None, "checked": False},
                    {"id": "2", "content": "File expenses", "description": "n",
                     "due": {"date": "2026-09-04"}, "checked": False},
                    {"id": "3", "content": "Old thing", "description": "",
                     "due": {"date": "2026-01-01"}, "checked": False},
                ],
                "next_cursor": None,
            }
        if path == "/tasks/completed/by_completion_date":
            return {
                "results": [
                    {"id": "4", "content": "Ship the fix", "description": "",
                     "due": None, "checked": True,
                     "completed_at": "2026-09-04T12:00:00.000000Z"},
                ],
                "next_cursor": None,
            }
        return {"id": "new"}

    monkeypatch.setattr(TodoistProvider, "_request", fake_request)
    monkeypatch.setattr("app.providers.todoist._today", lambda: "2026-09-04")
    return calls


def test_satisfies_the_protocol():
    assert isinstance(TodoistProvider("t"), base.TaskProvider)


def test_sorts_into_buckets(fake_api):
    out = TodoistProvider("t").list_tasks()
    assert [t["title"] for t in out["undated"]] == ["Water the plants"]
    assert [t["title"] for t in out["due_today"]] == ["File expenses"]
    assert [t["title"] for t in out["overdue"]] == ["Old thing"]
    assert [t["title"] for t in out["done_today"]] == ["Ship the fix"]


def test_completed_call_sends_the_required_window(fake_api):
    TodoistProvider("t").list_tasks()
    done = [c for c in fake_api if c["path"].endswith("by_completion_date")][0]
    assert "since" in done["params"] and "until" in done["params"]


def test_notes_come_from_description(fake_api):
    out = TodoistProvider("t").list_tasks()
    assert out["due_today"][0]["notes"] == "n"


def test_complete_posts_to_close(fake_api):
    TodoistProvider("t").complete("9")
    assert fake_api[-1] == {
        "method": "POST", "path": "/tasks/9/close", "params": None, "body": None,
    }


def test_uncomplete_posts_to_reopen(fake_api):
    TodoistProvider("t").uncomplete("9")
    assert fake_api[-1]["path"] == "/tasks/9/reopen"


def test_create_sends_content_and_due(fake_api):
    TodoistProvider("t").create("New", notes="d", due="2026-09-05")
    body = fake_api[-1]["body"]
    assert body["content"] == "New"
    assert body["description"] == "d"
    assert body["due_date"] == "2026-09-05"


def test_check_reports_a_bad_token(monkeypatch):
    def boom(self, method, path, params=None, body=None):
        raise RuntimeError("HTTP 401")

    monkeypatch.setattr(TodoistProvider, "_request", boom)
    ok, msg = TodoistProvider("bad").check()
    assert ok is False
    assert "401" in msg
