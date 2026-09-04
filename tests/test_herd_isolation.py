"""A test instance must never write into the real herd.

Both the herd and the picks file were module-level constants pinned to the
repo root, so HERD_HOME had no effect on them. A browser check against a
scratch instance wrote a cat into the production herd, and undoing it threw
away a rose quartz roll that cannot be recovered.
"""

import json

from app import cats, paths, picks


def test_the_herd_follows_herd_home(tmp_home):
    cats._save({"days": {"2026-09-04": [{"for": "x"}]}, "total": 1})
    assert (tmp_home / "herd.json").exists()
    assert json.loads((tmp_home / "herd.json").read_text())["total"] == 1


def test_picks_follow_herd_home(tmp_home, monkeypatch):
    monkeypatch.setattr(picks.state, "working_day", lambda: "2026-09-04")
    picks.toggle("abc")
    assert (tmp_home / "picks.json").exists()


def test_the_repo_root_is_never_written(tmp_home):
    from pathlib import Path

    repo_root = Path(cats.__file__).parent.parent
    before = (repo_root / "herd.json").read_text() if (repo_root / "herd.json").exists() else None

    cats._save({"days": {}, "total": 0})

    after = (repo_root / "herd.json").read_text() if (repo_root / "herd.json").exists() else None
    assert before == after, "writing with HERD_HOME set still touched the repo-root herd"


def test_a_fresh_home_can_take_a_completion(tmp_home):
    """append_done on a brand new HERD_HOME used to raise FileNotFoundError,
    because nothing created the daily directory before writing into it."""
    from app import state

    state.append_done("Something finished")
    assert (tmp_home / "daily").is_dir()
    assert "Something finished" in state.day_file()
