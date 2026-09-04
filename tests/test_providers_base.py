from app.providers import base


def test_task_row_fills_every_key():
    row = base.task_row(id="1", title="Write the thing")
    assert row == {
        "id": "1",
        "title": "Write the thing",
        "due": "",
        "notes": "",
    }


def test_task_row_keeps_what_it_is_given():
    row = base.task_row(id="2", title="x", due="2026-09-04", notes="n")
    assert row["due"] == "2026-09-04"
    assert row["notes"] == "n"


def test_empty_tasks_has_every_bucket():
    assert set(base.EMPTY_TASKS()) == {
        "picked", "due_today", "overdue", "undated", "done_today",
    }
    assert all(v == [] for v in base.EMPTY_TASKS().values())


def test_a_minimal_provider_satisfies_the_protocol():
    class Fake:
        name = "fake"

        def check(self):
            return True, "ok"

        def list_tasks(self):
            return base.EMPTY_TASKS()

        def complete(self, task_id):
            return {}

        def uncomplete(self, task_id):
            return {}

        def create(self, title, notes="", due=None):
            return {"id": "1"}

    assert isinstance(Fake(), base.TaskProvider)
