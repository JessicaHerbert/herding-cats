import pytest

from app.providers import base
from app.providers.localfile import LocalFileProvider


@pytest.fixture
def provider(tmp_path):
    f = tmp_path / "tasks.md"
    f.write_text(
        "- [ ] Water the plants\n"
        "- [ ] File expenses (due 2026-09-04)\n"
        "- [ ] Old thing (due 2026-01-01)\n"
        "- [x] Ship the fix (done 2026-09-04)\n"
    )
    return LocalFileProvider(str(f))


def test_satisfies_the_protocol(provider):
    assert isinstance(provider, base.TaskProvider)


def test_check_passes_when_the_file_is_there(provider):
    ok, _ = provider.check()
    assert ok is True


def test_check_fails_with_a_useful_message(tmp_path):
    p = LocalFileProvider(str(tmp_path / "missing.md"))
    ok, msg = p.check()
    assert ok is False
    assert "missing.md" in msg


def test_sorts_into_buckets(provider, monkeypatch):
    monkeypatch.setattr("app.providers.localfile._today", lambda: "2026-09-04")
    out = provider.list_tasks()
    assert [t["title"] for t in out["undated"]] == ["Water the plants"]
    assert [t["title"] for t in out["due_today"]] == ["File expenses"]
    assert [t["title"] for t in out["overdue"]] == ["Old thing"]
    assert [t["title"] for t in out["done_today"]] == ["Ship the fix"]


def test_ids_are_stable_across_reads(provider):
    first = provider.list_tasks()["undated"][0]["id"]
    second = provider.list_tasks()["undated"][0]["id"]
    assert first == second


def test_create_appends(provider, monkeypatch):
    monkeypatch.setattr("app.providers.localfile._today", lambda: "2026-09-04")
    provider.create("New task")
    titles = [t["title"] for t in provider.list_tasks()["undated"]]
    assert "New task" in titles


def test_complete_then_uncomplete_round_trips(provider, monkeypatch):
    monkeypatch.setattr("app.providers.localfile._today", lambda: "2026-09-04")
    task_id = provider.list_tasks()["undated"][0]["id"]
    provider.complete(task_id)
    assert "Water the plants" in [
        t["title"] for t in provider.list_tasks()["done_today"]
    ]
    provider.uncomplete(task_id)
    assert "Water the plants" in [
        t["title"] for t in provider.list_tasks()["undated"]
    ]
