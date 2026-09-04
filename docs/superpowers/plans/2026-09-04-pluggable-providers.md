# Pluggable Providers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let anyone clone this repo and run it against their own task manager, mail, timezone, and schedule, with a first-run wizard and no source edits.

**Architecture:** A provider seam codifies the normalized shapes `state.tasks()` and `mail.waiting()` already return. Config and data move to `~/.herding-cats/` under a `HERD_HOME` root, read from `config.toml` via stdlib `tomllib`. Existing Google code moves behind the seam unchanged, then `localfile` and `todoist` join it.

**Tech Stack:** Python 3.11, FastAPI, stdlib `tomllib` and `urllib`, pytest. No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-09-04-pluggable-providers-design.md`

## Global Constraints

- Python `>=3.11`. `tomllib` is stdlib; do not add a TOML parser.
- No new runtime dependencies. Todoist uses `urllib.request`, not `requests`. pytest is a dev dependency only.
- Never use `rm`. Use `trash` for any deletion.
- `herd.json`, `picks.json`, `.env`, and `herd.backup-*.json` stay gitignored. Never commit real task text.
- Existing `HERD_TASKLIST` and `HERD_EMAIL` env vars must keep working as overrides.
- The 6am default and the existing duplicate-cat fix must not regress.
- American spelling. No em dashes or en dashes in code, comments, or docs.
- Todoist API facts, verified against the live OpenAPI spec on 2026-09-04:
  - Base URL `https://api.todoist.com/api/v1`. The older `/rest/v2/` returns HTTP 410 Gone; do not use it.
  - Auth header `Authorization: Bearer <token>`.
  - `GET /tasks` returns `{"results": [...], "next_cursor": null|str}`. It returns ACTIVE tasks only and has NO completed or date filter.
  - Completed tasks come from `GET /tasks/completed/by_completion_date`, which REQUIRES `since` and `until` and caps the range at 3 months.
  - Task fields: `id` (string), `content` (title), `description` (notes), `due` (object or null, shaped `{"date": "2025-02-12", "is_recurring": false, ...}`), `checked` (bool), `completed_at` (string or null).
  - Close is `POST /tasks/{id}/close`, reopen is `POST /tasks/{id}/reopen`, create is `POST /tasks`.

---

## File Structure

| File | Responsibility |
|---|---|
| `app/paths.py` | Resolve `HERD_HOME` and every path under it |
| `app/config.py` | Load and validate `config.toml`, apply env overrides and defaults |
| `app/migrate.py` | Copy-verify-delete old data into `HERD_HOME` |
| `app/providers/base.py` | `TaskProvider` and `MailProvider` protocols, shared row shapes |
| `app/providers/__init__.py` | Resolve the configured provider, cache it, `calendar_or_none()` |
| `app/providers/google_tasks.py` | Existing `gws` task code, moved |
| `app/providers/gmail.py` | Existing `mail.py` code, moved |
| `app/providers/localfile.py` | Tasks from a markdown file, no auth |
| `app/providers/todoist.py` | Todoist REST over `urllib` |
| `app/setup.py` | First-run terminal wizard |
| `tests/` | pytest suite |

---

### Task 1: Test infrastructure

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/__init__.py`, `tests/conftest.py`, `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing
- Produces: a `tmp_home` fixture returning a `Path` that later tasks use as `HERD_HOME`

- [ ] **Step 1: Add pytest as a dev dependency**

In `pyproject.toml`, after the `dependencies` list:

```toml
[dependency-groups]
dev = ["pytest>=8.0"]
```

- [ ] **Step 2: Install it**

Run: `uv sync --group dev`
Expected: pytest installs into `.venv`.

- [ ] **Step 3: Write the fixture and a smoke test**

`tests/__init__.py` is empty. `tests/conftest.py`:

```python
import pytest


@pytest.fixture
def tmp_home(tmp_path, monkeypatch):
    """An isolated HERD_HOME, so tests never touch the real herd."""
    home = tmp_path / "herd-home"
    home.mkdir()
    monkeypatch.setenv("HERD_HOME", str(home))
    return home
```

`tests/test_smoke.py`:

```python
def test_app_imports():
    from app import cats, rollover, state
    assert cats and rollover and state


def test_tmp_home_is_isolated(tmp_home):
    import os
    assert os.environ["HERD_HOME"] == str(tmp_home)
    assert tmp_home.is_dir()
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock tests/
git commit -m "Add pytest and an isolated HERD_HOME fixture"
```

---

### Task 2: Path resolution

**Files:**
- Create: `app/paths.py`, `tests/test_paths.py`

**Interfaces:**
- Consumes: nothing
- Produces: `home() -> Path`, `config_file() -> Path`, `herd_file() -> Path`, `picks_file() -> Path`, `daily_dir() -> Path`, `ensure() -> Path`

- [ ] **Step 1: Write the failing test**

`tests/test_paths.py`:

```python
from pathlib import Path

from app import paths


def test_home_defaults_to_dot_herding_cats(monkeypatch):
    monkeypatch.delenv("HERD_HOME", raising=False)
    assert paths.home() == Path.home() / ".herding-cats"


def test_home_respects_env(tmp_home):
    assert paths.home() == tmp_home


def test_everything_hangs_off_home(tmp_home):
    assert paths.config_file() == tmp_home / "config.toml"
    assert paths.herd_file() == tmp_home / "herd.json"
    assert paths.picks_file() == tmp_home / "picks.json"
    assert paths.daily_dir() == tmp_home / "daily"


def test_ensure_creates_the_tree(tmp_path, monkeypatch):
    target = tmp_path / "fresh"
    monkeypatch.setenv("HERD_HOME", str(target))
    paths.ensure()
    assert target.is_dir()
    assert (target / "daily").is_dir()


def test_tilde_in_env_is_expanded(monkeypatch):
    monkeypatch.setenv("HERD_HOME", "~/somewhere-else")
    assert paths.home() == Path.home() / "somewhere-else"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_paths.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.paths'`.

- [ ] **Step 3: Write the implementation**

`app/paths.py`:

```python
"""Where your config and data live.

Everything hangs off one root so the app can be moved, reinstalled, or
cloned fresh without losing the herd, and so a public checkout never holds
real task text.
"""

import os
from pathlib import Path

DEFAULT_HOME = "~/.herding-cats"


def home() -> Path:
    return Path(os.environ.get("HERD_HOME") or DEFAULT_HOME).expanduser()


def config_file() -> Path:
    return home() / "config.toml"


def herd_file() -> Path:
    return home() / "herd.json"


def picks_file() -> Path:
    return home() / "picks.json"


def daily_dir() -> Path:
    return home() / "daily"


def ensure() -> Path:
    """Create the tree if it is not there yet. Returns the root."""
    root = home()
    root.mkdir(parents=True, exist_ok=True)
    daily_dir().mkdir(parents=True, exist_ok=True)
    return root
```

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/bin/pytest tests/test_paths.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add app/paths.py tests/test_paths.py
git commit -m "Resolve every path from one HERD_HOME root"
```

---

### Task 3: Config loading

**Files:**
- Create: `app/config.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: `app.paths.config_file()`
- Produces: `load() -> dict` (cached), `reload() -> dict`, `exists() -> bool`, `ConfigError`

The returned dict always has this shape, defaults filled in:

```python
{
  "general": {"timezone": str, "day_starts_at": int},
  "tasks": {"provider": str, "tasklist": str, "token": str, "path": str},
  "mail": {"provider": str, "address": str},
}
```

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:

```python
import pytest

from app import config


def test_defaults_when_no_file(tmp_home, monkeypatch):
    monkeypatch.delenv("HERD_TASKLIST", raising=False)
    monkeypatch.delenv("HERD_EMAIL", raising=False)
    cfg = config.reload()
    assert cfg["general"]["day_starts_at"] == 6
    assert cfg["general"]["timezone"]
    assert cfg["tasks"]["provider"] == "google"
    assert cfg["mail"]["provider"] == "gmail"


def test_reads_the_file(tmp_home):
    (tmp_home / "config.toml").write_text(
        '[general]\ntimezone = "UTC"\nday_starts_at = 4\n'
        '[tasks]\nprovider = "localfile"\npath = "/tmp/t.md"\n'
        '[mail]\nprovider = "none"\n'
    )
    cfg = config.reload()
    assert cfg["general"]["timezone"] == "UTC"
    assert cfg["general"]["day_starts_at"] == 4
    assert cfg["tasks"]["provider"] == "localfile"
    assert cfg["mail"]["provider"] == "none"


def test_env_overrides_file(tmp_home, monkeypatch):
    (tmp_home / "config.toml").write_text(
        '[tasks]\nprovider = "google"\ntasklist = "from-file"\n'
    )
    monkeypatch.setenv("HERD_TASKLIST", "from-env")
    monkeypatch.setenv("HERD_EMAIL", "me@example.com")
    cfg = config.reload()
    assert cfg["tasks"]["tasklist"] == "from-env"
    assert cfg["mail"]["address"] == "me@example.com"


def test_bad_toml_is_a_clear_error(tmp_home):
    (tmp_home / "config.toml").write_text("this is not = = toml")
    with pytest.raises(config.ConfigError) as e:
        config.reload()
    assert "config.toml" in str(e.value)


def test_unknown_provider_is_rejected(tmp_home):
    (tmp_home / "config.toml").write_text('[tasks]\nprovider = "nope"\n')
    with pytest.raises(config.ConfigError) as e:
        config.reload()
    assert "nope" in str(e.value)


def test_exists_reflects_the_file(tmp_home):
    assert config.exists() is False
    (tmp_home / "config.toml").write_text('[tasks]\nprovider = "localfile"\n')
    assert config.exists() is True
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL, no module named `app.config`.

- [ ] **Step 3: Write the implementation**

`app/config.py`:

```python
"""Read config.toml, fill in defaults, let env vars win.

Env overrides exist so an installation that predates the config file keeps
working: HERD_TASKLIST and HERD_EMAIL were the original settings.
"""

import os
import tomllib
from datetime import datetime

from . import paths

TASK_PROVIDERS = ("google", "todoist", "localfile")
MAIL_PROVIDERS = ("gmail", "none")

_cache: dict | None = None


class ConfigError(Exception):
    pass


def _system_timezone() -> str:
    tz = datetime.now().astimezone().tzinfo
    return str(tz) if tz else "UTC"


def _defaults() -> dict:
    return {
        "general": {"timezone": _system_timezone(), "day_starts_at": 6},
        "tasks": {"provider": "google", "tasklist": "", "token": "", "path": ""},
        "mail": {"provider": "gmail", "address": ""},
    }


def exists() -> bool:
    return paths.config_file().exists()


def reload() -> dict:
    global _cache

    cfg = _defaults()
    path = paths.config_file()
    if path.exists():
        try:
            raw = tomllib.loads(path.read_text())
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{path} is not valid TOML: {exc}") from exc
        for section, values in raw.items():
            if section in cfg and isinstance(values, dict):
                cfg[section].update(values)

    if os.environ.get("HERD_TASKLIST"):
        cfg["tasks"]["tasklist"] = os.environ["HERD_TASKLIST"]
    if os.environ.get("HERD_EMAIL"):
        cfg["mail"]["address"] = os.environ["HERD_EMAIL"]

    if cfg["tasks"]["provider"] not in TASK_PROVIDERS:
        raise ConfigError(
            f"unknown task provider {cfg['tasks']['provider']!r}, "
            f"expected one of {', '.join(TASK_PROVIDERS)}"
        )
    if cfg["mail"]["provider"] not in MAIL_PROVIDERS:
        raise ConfigError(
            f"unknown mail provider {cfg['mail']['provider']!r}, "
            f"expected one of {', '.join(MAIL_PROVIDERS)}"
        )
    try:
        cfg["general"]["day_starts_at"] = int(cfg["general"]["day_starts_at"])
    except (TypeError, ValueError) as exc:
        raise ConfigError("day_starts_at must be a whole number of hours") from exc

    _cache = cfg
    return cfg


def load() -> dict:
    return _cache if _cache is not None else reload()
```

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "Load config.toml with defaults and env overrides"
```

---

### Task 4: Migration

**Files:**
- Create: `app/migrate.py`, `tests/test_migrate.py`

**Interfaces:**
- Consumes: `app.paths`
- Produces: `find_old() -> dict[str, Path]`, `run(sources: dict) -> dict[str, int]`

- [ ] **Step 1: Write the failing test**

`tests/test_migrate.py`:

```python
import json

from app import migrate, paths


def test_finds_nothing_when_there_is_nothing(tmp_home, tmp_path):
    assert migrate.find_old(repo_root=tmp_path, old_daily=tmp_path / "nope") == {}


def test_finds_old_data(tmp_home, tmp_path):
    (tmp_path / "herd.json").write_text('{"days": {}, "total": 0}')
    old_daily = tmp_path / "daily"
    old_daily.mkdir()
    (old_daily / "2026-09-01.md").write_text("# day")
    found = migrate.find_old(repo_root=tmp_path, old_daily=old_daily)
    assert "herd" in found and "daily" in found


def test_run_moves_and_verifies(tmp_home, tmp_path):
    herd = {"days": {"2026-09-01": [{"for": "a"}, {"for": "b"}]}, "total": 2}
    (tmp_path / "herd.json").write_text(json.dumps(herd))
    old_daily = tmp_path / "daily"
    old_daily.mkdir()
    (old_daily / "2026-09-01.md").write_text("# day one")
    (old_daily / "2026-09-02.md").write_text("# day two")

    found = migrate.find_old(repo_root=tmp_path, old_daily=old_daily)
    result = migrate.run(found)

    assert result["cats"] == 2
    assert result["daily"] == 2
    moved = json.loads(paths.herd_file().read_text())
    assert moved["total"] == 2
    assert (paths.daily_dir() / "2026-09-02.md").read_text() == "# day two"
    assert not (tmp_path / "herd.json").exists()


def test_original_survives_a_bad_copy(tmp_home, tmp_path):
    (tmp_path / "herd.json").write_text("{ not json")
    found = migrate.find_old(repo_root=tmp_path, old_daily=tmp_path / "nope")
    result = migrate.run(found)
    assert result["cats"] == 0
    assert (tmp_path / "herd.json").exists()


def test_never_overwrites_existing(tmp_home, tmp_path):
    paths.ensure()
    paths.herd_file().write_text('{"days": {}, "total": 99}')
    (tmp_path / "herd.json").write_text('{"days": {}, "total": 1}')
    found = migrate.find_old(repo_root=tmp_path, old_daily=tmp_path / "nope")
    migrate.run(found)
    assert json.loads(paths.herd_file().read_text())["total"] == 99
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_migrate.py -v`
Expected: FAIL, no module named `app.migrate`.

- [ ] **Step 3: Write the implementation**

`app/migrate.py`:

```python
"""Move an existing herd into HERD_HOME.

Copy, verify the copy, then remove the original. Never a bare move: the herd
is gitignored and has no history to fall back on, so a half-finished move
would lose it.
"""

import json
import shutil
from pathlib import Path

from . import paths

OLD_DAILY = Path.home() / "tools-and-projects" / "rosie" / "daily"


def find_old(repo_root: Path | None = None, old_daily: Path | None = None) -> dict:
    """Old-layout data worth moving, keyed by what it is."""
    root = repo_root or Path(__file__).parent.parent
    daily = old_daily if old_daily is not None else OLD_DAILY

    found = {}
    if (root / "herd.json").exists() and not paths.herd_file().exists():
        found["herd"] = root / "herd.json"
    if (root / "picks.json").exists() and not paths.picks_file().exists():
        found["picks"] = root / "picks.json"
    if daily.is_dir() and any(daily.glob("*.md")):
        found["daily"] = daily
    return found


def _move_json(src: Path, dst: Path) -> int:
    """Copy a JSON file, confirm it parses, then drop the original."""
    try:
        parsed = json.loads(src.read_text())
    except json.JSONDecodeError:
        return 0
    dst.write_text(json.dumps(parsed, indent=2))
    if json.loads(dst.read_text()) != parsed:
        return 0
    src.unlink()
    return sum(len(v) for v in parsed.get("days", {}).values())


def run(sources: dict) -> dict:
    """Move what find_old turned up. Returns what moved."""
    paths.ensure()
    result = {"cats": 0, "picks": 0, "daily": 0}

    if "herd" in sources:
        result["cats"] = _move_json(sources["herd"], paths.herd_file())

    if "picks" in sources and not paths.picks_file().exists():
        moved = _move_json(sources["picks"], paths.picks_file())
        result["picks"] = 1 if moved >= 0 and paths.picks_file().exists() else 0

    if "daily" in sources:
        for md in sorted(sources["daily"].glob("*.md")):
            target = paths.daily_dir() / md.name
            if target.exists():
                continue
            shutil.copy2(md, target)
            if target.read_text() == md.read_text():
                md.unlink()
                result["daily"] += 1
    return result
```

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/bin/pytest tests/test_migrate.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add app/migrate.py tests/test_migrate.py
git commit -m "Migrate an existing herd into HERD_HOME, copy-verify-delete"
```

---

### Task 5: Provider protocols

**Files:**
- Create: `app/providers/__init__.py`, `app/providers/base.py`, `tests/test_providers_base.py`

**Interfaces:**
- Consumes: nothing
- Produces: `TaskProvider`, `MailProvider`, `EMPTY_TASKS`, `task_row()`

- [ ] **Step 1: Write the failing test**

`tests/test_providers_base.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_providers_base.py -v`
Expected: FAIL, no module named `app.providers`.

- [ ] **Step 3: Write the implementation**

`app/providers/__init__.py` is empty for now. `app/providers/base.py`:

```python
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
```

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/bin/pytest tests/test_providers_base.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/providers/ tests/test_providers_base.py
git commit -m "Define the task and mail provider protocols"
```

---

### Task 6: Local file provider

**Files:**
- Create: `app/providers/localfile.py`, `tests/test_localfile.py`

**Interfaces:**
- Consumes: `app.providers.base`
- Produces: `LocalFileProvider(path)` satisfying `TaskProvider`

File format, one task per line:

```markdown
- [ ] Water the plants
- [ ] File expenses (due 2026-09-04)
- [x] Ship the fix (done 2026-09-04)
```

- [ ] **Step 1: Write the failing test**

`tests/test_localfile.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_localfile.py -v`
Expected: FAIL, no module named `app.providers.localfile`.

- [ ] **Step 3: Write the implementation**

`app/providers/localfile.py`:

```python
"""Tasks from a markdown file. No account, no network, no auth.

This is also the honesty test for the provider seam: with no server and no
assigned ids, anything Google-shaped that leaked into the interface would
show up here immediately.
"""

import hashlib
import re
from datetime import datetime
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
```

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/bin/pytest tests/test_localfile.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add app/providers/localfile.py tests/test_localfile.py
git commit -m "Add a local markdown task provider that needs no account"
```

---

### Task 7: Todoist provider

**Files:**
- Create: `app/providers/todoist.py`, `tests/test_todoist.py`

**Interfaces:**
- Consumes: `app.providers.base`
- Produces: `TodoistProvider(token)` satisfying `TaskProvider`

Re-read the Todoist facts in Global Constraints before writing this. The `/rest/v2/` API is gone and completed tasks need their own endpoint.

- [ ] **Step 1: Write the failing test**

`tests/test_todoist.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_todoist.py -v`
Expected: FAIL, no module named `app.providers.todoist`.

- [ ] **Step 3: Write the implementation**

`app/providers/todoist.py`:

```python
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
```

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/bin/pytest tests/test_todoist.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add app/providers/todoist.py tests/test_todoist.py
git commit -m "Add a Todoist provider on the v1 REST API"
```

---

### Task 8: Move Google and Gmail behind the seam

**Files:**
- Create: `app/providers/google_tasks.py`, `app/providers/gmail.py`
- Modify: `app/providers/__init__.py`, `app/state.py`, `app/mail.py`, `app/main.py`
- Create: `tests/test_provider_resolution.py`

**Interfaces:**
- Consumes: every provider from Tasks 5 to 7
- Produces: `providers.tasks() -> TaskProvider`, `providers.mail() -> MailProvider | None`, `providers.calendar_or_none()`, `providers.reset()`

This is a move, not a rewrite. `GoogleTasksProvider` wraps the existing `_gws` calls from `state.py`; `GmailProvider` wraps `mail.waiting`. Behavior must not change.

- [ ] **Step 1: Write the failing test**

`tests/test_provider_resolution.py`:

```python
import pytest

from app import config, providers


def test_localfile_resolves(tmp_home, monkeypatch):
    f = tmp_home / "tasks.md"
    f.write_text("- [ ] hi\n")
    (tmp_home / "config.toml").write_text(
        f'[tasks]\nprovider = "localfile"\npath = "{f}"\n'
        '[mail]\nprovider = "none"\n'
    )
    config.reload()
    providers.reset()
    assert providers.tasks().name == "localfile"


def test_todoist_resolves(tmp_home):
    (tmp_home / "config.toml").write_text(
        '[tasks]\nprovider = "todoist"\ntoken = "abc"\n'
        '[mail]\nprovider = "none"\n'
    )
    config.reload()
    providers.reset()
    assert providers.tasks().name == "todoist"


def test_mail_none_returns_none(tmp_home):
    (tmp_home / "config.toml").write_text(
        '[tasks]\nprovider = "todoist"\ntoken = "abc"\n'
        '[mail]\nprovider = "none"\n'
    )
    config.reload()
    providers.reset()
    assert providers.mail() is None


def test_calendar_is_none_when_tasks_are_not_google(tmp_home):
    (tmp_home / "config.toml").write_text(
        '[tasks]\nprovider = "todoist"\ntoken = "abc"\n'
        '[mail]\nprovider = "none"\n'
    )
    config.reload()
    providers.reset()
    assert providers.calendar_or_none() is None


def test_the_provider_is_cached(tmp_home):
    (tmp_home / "config.toml").write_text(
        '[tasks]\nprovider = "todoist"\ntoken = "abc"\n'
        '[mail]\nprovider = "none"\n'
    )
    config.reload()
    providers.reset()
    assert providers.tasks() is providers.tasks()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_provider_resolution.py -v`
Expected: FAIL, `providers` has no attribute `tasks`.

- [ ] **Step 3: Write the two Google providers**

`app/providers/google_tasks.py` holds `GoogleTasksProvider` with `name = "google"`. Move the body of the current `state.tasks()`, `state.complete_task()`, `state.uncomplete_task()`, and `state.create_task()` into `list_tasks`, `complete`, `uncomplete`, and `create`, along with the `_gws` helper, `_local_date`, and `_completed_date`. Keep `picks` integration exactly as it is. `check()` runs `gws tasks tasklists list` and returns `(False, "the gws CLI is not installed or not authenticated")` when the subprocess fails.

`app/providers/gmail.py` holds `GmailProvider` with `name = "gmail"`, wrapping the existing `mail.waiting()` body unchanged, with `ME` read from config rather than the module-level env read. `check()` runs a one-thread list and reports failure the same way.

- [ ] **Step 4: Write the resolver**

`app/providers/__init__.py`:

```python
"""Pick the configured backend and hand it to the rest of the app."""

from .. import config

_tasks = None
_mail = None
_calendar = None
_resolved = False


def reset() -> None:
    """Drop the cache. Used by the wizard and by tests."""
    global _tasks, _mail, _calendar, _resolved
    _tasks = _mail = _calendar = None
    _resolved = False


def _resolve() -> None:
    global _tasks, _mail, _calendar, _resolved
    if _resolved:
        return
    cfg = config.load()

    which = cfg["tasks"]["provider"]
    if which == "localfile":
        from .localfile import LocalFileProvider

        _tasks = LocalFileProvider(cfg["tasks"]["path"])
    elif which == "todoist":
        from .todoist import TodoistProvider

        _tasks = TodoistProvider(cfg["tasks"]["token"])
    else:
        from .google_tasks import GoogleTasksProvider

        _tasks = GoogleTasksProvider(cfg["tasks"]["tasklist"])

    if cfg["mail"]["provider"] == "gmail":
        from .gmail import GmailProvider

        _mail = GmailProvider(cfg["mail"]["address"])
    else:
        _mail = None

    # Calendar is Google's alone. Todoist and a text file have none, so the
    # dashboard drops the column rather than pretending.
    if which == "google":
        from .google_tasks import GoogleCalendar

        _calendar = GoogleCalendar()
    else:
        _calendar = None
    _resolved = True


def tasks():
    _resolve()
    return _tasks


def mail():
    _resolve()
    return _mail


def calendar_or_none():
    _resolve()
    return _calendar
```

- [ ] **Step 5: Point the callers at the seam**

In `app/state.py`, replace the bodies of `tasks`, `complete_task`, `uncomplete_task`, and `create_task` with delegations, keeping the names so `main.py` does not change:

```python
def tasks() -> dict:
    from . import providers

    return providers.tasks().list_tasks()


def complete_task(task_id: str) -> dict:
    from . import providers

    return providers.tasks().complete(task_id)


def uncomplete_task(task_id: str) -> dict:
    from . import providers

    return providers.tasks().uncomplete(task_id)


def create_task(title: str, notes: str = "", due: str | None = None) -> dict:
    from . import providers

    return providers.tasks().create(title, notes, due)


def calendar() -> dict:
    from . import providers

    cal = providers.calendar_or_none()
    return cal.today() if cal else {"events": [], "collisions": []}
```

In `app/main.py`, guard the mail endpoint so a `none` provider returns an empty list rather than raising:

```python
@app.get("/api/mail")
async def get_mail():
    from . import providers

    provider = providers.mail()
    if provider is None:
        return {"threads": []}
    ...
```

- [ ] **Step 6: Run the whole suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: every test passes, including the earlier ones.

- [ ] **Step 7: Check the real app still works**

Run: `.venv/bin/python -c "import sys; sys.path.insert(0,'.'); from app import main, state, providers; print(providers.tasks().name); print(sorted(state.tasks()))"`
Expected: prints `google` and the five bucket names, against your real task list.

- [ ] **Step 8: Commit**

```bash
git add app/providers/ app/state.py app/mail.py app/main.py tests/test_provider_resolution.py
git commit -m "Move Google Tasks and Gmail behind the provider seam"
```

---

### Task 9: Timezone and day boundary from config

**Files:**
- Modify: `app/state.py:12`, `app/state.py:28`, `app/state.py:31-44`
- Create: `tests/test_day_boundary.py`

**Interfaces:**
- Consumes: `app.config.load()`
- Produces: unchanged public names `today()`, `working_day()`

- [ ] **Step 1: Write the failing test**

`tests/test_day_boundary.py`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app import config, state


@pytest.fixture
def utc_config(tmp_home):
    (tmp_home / "config.toml").write_text(
        '[general]\ntimezone = "UTC"\nday_starts_at = 6\n'
        '[tasks]\nprovider = "localfile"\npath = "/tmp/t.md"\n'
        '[mail]\nprovider = "none"\n'
    )
    config.reload()


def test_before_the_boundary_is_yesterday(utc_config, monkeypatch):
    fixed = datetime(2026, 9, 4, 1, 5, tzinfo=ZoneInfo("UTC"))
    monkeypatch.setattr(state, "today", lambda: fixed)
    assert state.working_day() == "2026-09-03"


def test_after_the_boundary_is_today(utc_config, monkeypatch):
    fixed = datetime(2026, 9, 4, 6, 1, tzinfo=ZoneInfo("UTC"))
    monkeypatch.setattr(state, "today", lambda: fixed)
    assert state.working_day() == "2026-09-04"


def test_a_custom_boundary_is_honored(tmp_home, monkeypatch):
    (tmp_home / "config.toml").write_text(
        '[general]\ntimezone = "UTC"\nday_starts_at = 4\n'
        '[tasks]\nprovider = "localfile"\npath = "/tmp/t.md"\n'
        '[mail]\nprovider = "none"\n'
    )
    config.reload()
    fixed = datetime(2026, 9, 4, 5, 0, tzinfo=ZoneInfo("UTC"))
    monkeypatch.setattr(state, "today", lambda: fixed)
    assert state.working_day() == "2026-09-04"


def test_timezone_comes_from_config(utc_config):
    assert str(state.tz()) == "UTC"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_day_boundary.py -v`
Expected: FAIL, `state` has no attribute `tz`.

- [ ] **Step 3: Replace the constants with config reads**

In `app/state.py`, delete `TZ = ZoneInfo(...)` and `DAY_STARTS_AT = 6`, and delete `DAILY_DIR`. Add:

```python
def tz() -> ZoneInfo:
    from . import config

    try:
        return ZoneInfo(config.load()["general"]["timezone"])
    except Exception:
        return ZoneInfo("UTC")


def day_starts_at() -> int:
    from . import config

    return config.load()["general"]["day_starts_at"]


def today() -> datetime:
    return datetime.now(tz())


def working_day() -> str:
    """The day the pile belongs to, on a configurable boundary.

    Work finished at 00:30 belongs to the night before, not to a fresh day
    nobody has started yet.
    """
    now = today()
    if now.hour < day_starts_at():
        now -= timedelta(days=1)
    return now.strftime("%Y-%m-%d")
```

Update `_completed_date` to call `tz()` and `day_starts_at()` instead of the deleted constants, and point `day_file_path` at `paths.daily_dir()`.

- [ ] **Step 4: Run the whole suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: all pass. The duplicate-cat behavior must be unchanged.

- [ ] **Step 5: Commit**

```bash
git add app/state.py tests/test_day_boundary.py
git commit -m "Read timezone and the day boundary from config"
```

---

### Task 10: Standalone UI for logging done work and adding a task

**Files:**
- Modify: `web/index.html`, `web/app.js`, `web/app.css`

**Interfaces:**
- Consumes: existing `POST /api/done` and `POST /api/task`
- Produces: nothing other tasks depend on

No backend change. Both endpoints exist and the skill already uses them.

- [ ] **Step 1: Add the two buttons**

In `web/index.html`, in the same header row as the existing refresh and mute controls:

```html
<button id="log-done" title="Log something you finished">+ done</button>
<button id="add-task" title="Add a task">+ task</button>
```

- [ ] **Step 2: Wire them up**

In `web/app.js`, next to the existing `mute` handler, following the same `prompt` idiom the note feature uses:

```js
$("log-done")?.addEventListener("click", async () => {
  const text = prompt("What did you finish?");
  if (!text || !text.trim()) return;
  await post("/api/done", { text: text.trim() });
  $("refresh").click();
});

$("add-task")?.addEventListener("click", async () => {
  const title = prompt("What needs doing?");
  if (!title || !title.trim()) return;
  await post("/api/task", { title: title.trim() });
  $("refresh").click();
});
```

- [ ] **Step 3: Style them like the existing header buttons**

In `web/app.css`, add `#log-done, #add-task` to whichever selector already styles the header buttons. Read the file first and match it rather than inventing a new rule.

- [ ] **Step 4: Check it in the real app**

Run: `.venv/bin/uvicorn app.main:app --port 8788 &` then open `http://localhost:8788`.
Click `+ done`, enter "Test the standalone log path", confirm a cat appears and the day file gains the line. Then remove that test cat with the existing undo so the herd stays honest.

- [ ] **Step 5: Commit**

```bash
git add web/index.html web/app.js web/app.css
git commit -m "Add UI for logging finished work and creating a task"
```

---

### Task 11: Setup wizard

**Files:**
- Create: `app/setup.py`, `tests/test_setup.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `app.config`, `app.paths`, `app.migrate`, every provider
- Produces: `run(input_fn=input, output_fn=print) -> Path`, `write_config(cfg) -> Path`, `needed() -> bool`

`input_fn` and `output_fn` are injected so the wizard is testable without a terminal.

- [ ] **Step 1: Write the failing test**

`tests/test_setup.py`:

```python
import tomllib

from app import paths, setup


def test_needed_when_no_config(tmp_home):
    assert setup.needed() is True


def test_not_needed_once_written(tmp_home):
    (tmp_home / "config.toml").write_text('[tasks]\nprovider = "localfile"\n')
    assert setup.needed() is False


def test_write_config_round_trips(tmp_home):
    cfg = {
        "general": {"timezone": "UTC", "day_starts_at": 5},
        "tasks": {"provider": "localfile", "path": "/tmp/t.md",
                  "token": "", "tasklist": ""},
        "mail": {"provider": "none", "address": ""},
    }
    written = setup.write_config(cfg)
    back = tomllib.loads(written.read_text())
    assert back["general"]["day_starts_at"] == 5
    assert back["tasks"]["provider"] == "localfile"
    assert back["mail"]["provider"] == "none"
    assert "token" not in back["tasks"]


def test_localfile_walkthrough(tmp_home):
    answers = iter(["UTC", "6", "3", str(tmp_home / "tasks.md"), "2", "n"])
    said = []
    setup.run(input_fn=lambda _="": next(answers), output_fn=said.append)

    cfg = tomllib.loads(paths.config_file().read_text())
    assert cfg["tasks"]["provider"] == "localfile"
    assert cfg["mail"]["provider"] == "none"
    assert (tmp_home / "tasks.md").exists()
    assert any("config.toml" in s for s in said)


def test_blank_answers_take_the_defaults(tmp_home):
    answers = iter(["", "", "3", str(tmp_home / "t.md"), "2", "n"])
    setup.run(input_fn=lambda _="": next(answers), output_fn=lambda _: None)
    cfg = tomllib.loads(paths.config_file().read_text())
    assert cfg["general"]["day_starts_at"] == 6
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_setup.py -v`
Expected: FAIL, no module named `app.setup`.

- [ ] **Step 3: Write the wizard**

`app/setup.py` implements:

- `needed()` returning `not config.exists()`
- `write_config(cfg)` emitting flat TOML by hand, three sections, skipping empty values so a Google config carries no stray `token = ""`, creating `paths.ensure()` first
- `run(input_fn, output_fn)` walking: timezone (default detected), day start (default 6), task provider by number (1 google, 2 todoist, 3 localfile), the provider's own follow-up question, mail provider (1 gmail, 2 none), then `check()` on each chosen provider with the failure message printed and the question re-asked, then migration if `migrate.find_old()` returns anything and the user answers yes, then write and print the path

For Google, list the available task lists with `gws tasks tasklists list` and let the user pick by number. If that call fails, say the `gws` CLI is missing or unauthenticated and offer the other providers.

For localfile, create the file with `LocalFileProvider.HEADER` if it does not exist.

- [ ] **Step 4: Hook it into startup**

In `app/main.py`, at import time:

```python
if setup.needed():
    raise SystemExit(
        "No config yet. Run:  .venv/bin/python -m app.setup"
    )
```

Add an `if __name__ == "__main__": run()` block to `app/setup.py` so `python -m app.setup` works.

- [ ] **Step 5: Run the suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app/setup.py app/main.py tests/test_setup.py
git commit -m "Add a first-run setup wizard that verifies before writing"
```

---

### Task 12: README, CLAUDE.md, and language pass

**Files:**
- Modify: `README.md`, `app/rollover.py:3`, `app/mail.py:1-8`, `app/picks.py:1-10`, `app/docs.py:38`, `app/docs.py:48`, `app/main.py:61`, `app/state.py:10`
- Create: `CLAUDE.md`

**Interfaces:**
- Consumes: nothing
- Produces: nothing

The test for this task is whether someone can hand the repo to a fresh
Claude Code session and have it work without asking questions. The current
README fails that: it tells the reader to edit constants in `app/state.py`
that Tasks 8 and 9 delete, and it links the `gws` CLI to a bare
`https://github.com/` with no repo path.

- [ ] **Step 1: Rewrite the README**

Sections in this order: what it is, install, `python -m app.setup`, the three task providers and two mail providers in a table, config reference with every key from Task 3, where data lives, adding your own provider (the two protocols from Task 5), and last a clearly marked "Optional: the Claude Code skill" section stating it needs Claude Code, that it sweeps and judges rather than just wrapping the API, and that `skill/SKILL.md` is one person's real working copy rather than a template.

Delete the two stale instructions: the "constants at the top of
`app/state.py`" line near the top, and the "set `TASKLIST` and `TZ` in
`app/state.py`" line under Running it. Both describe code that no longer
exists. Replace the dead `gws` link with the real one, or say plainly that
it is a personal CLI and name the Google provider's requirement instead.

- [ ] **Step 1b: Write CLAUDE.md**

An agent handed this repo reads `CLAUDE.md` first. Without one it has to
infer the venv convention, the test command, and which files must never be
committed. Cover, tersely:

- What the app is, in two sentences, and the split between the standalone
  dashboard and the optional skill
- Layout: `app/` backend, `app/providers/` the backends, `web/` frontend,
  `skill/` the optional Claude Code skill, `tests/` pytest
- Commands: `uv sync`, `.venv/bin/pytest tests/`, and how to run the app.
  State that `.venv/bin/python` is required because a bare `python3` lacks
  the dependencies
- Setup: `python -m app.setup` on first run, config at
  `~/.herding-cats/config.toml`
- Never commit: `herd.json`, `picks.json`, `.env`, `herd.backup-*.json`.
  Say why, which is that cat labels are real task text naming real people,
  and the repo is public
- Adding a provider: implement the protocol in `app/providers/base.py`,
  register it in `app/providers/__init__.py`, add it to the wizard's menu
  in `app/setup.py`
- The 6am day boundary and why it exists, since it is the single most
  surprising behavior in the codebase

- [ ] **Step 2: Neutralize the docstrings**

Replace third-person references to a specific person in the listed files with second person or a neutral subject. `skill/SKILL.md` is deliberately excluded and stays as it is.

Run: `grep -rniE "\bjess\b|\bshe\b|\bher\b" app/` and confirm the only hits left are in strings that genuinely need them, which should be none.

- [ ] **Step 3: Check the app still starts**

Run: `.venv/bin/pytest tests/ -v && .venv/bin/python -c "import sys; sys.path.insert(0,'.'); import app.main; print('ok')"`
Expected: tests pass and the import succeeds.

- [ ] **Step 4: Prove a stranger's clone works**

Documentation that has not been followed is a guess. Simulate a fresh
clone against the no-account provider, in a scratch directory outside the
repo:

```bash
cd /tmp && rm -rf herding-cats-freshclone
git clone /Users/jessicaherbert/tools-and-projects/rosie/herding-cats-app herding-cats-freshclone
cd herding-cats-freshclone
uv sync --group dev
HERD_HOME=/tmp/fresh-herd .venv/bin/pytest tests/ -q
```

Then walk the README's own setup steps verbatim with `HERD_HOME` pointed
at `/tmp/fresh-herd` and the `localfile` provider, and confirm the app
serves a dashboard. Any step that required knowledge not in `README.md` or
`CLAUDE.md` is a documentation bug: fix the docs, not the transcript.

Clean up with `trash /tmp/herding-cats-freshclone /tmp/fresh-herd` when
done. Note in the report which steps needed correcting.

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md app/
git commit -m "Document setup and providers, add CLAUDE.md, neutralize the voice"
```

---

## Self-Review

**Spec coverage.** Provider seam is Tasks 5 to 8. Paths and config are Tasks 2 and 3. Migration is Task 4. Timezone and day boundary are Task 9. Standalone UI is Task 10. Wizard is Task 11. README and language are Task 12. Testing requirements are folded into each task. Every spec section maps to a task.

**Placeholder scan.** Tasks 8, 11, and 12 describe moves and prose rather than quoting every line, which is deliberate: Task 8 is a mechanical relocation of code already in the repo, and quoting several hundred lines would invite drift from the original. Both name the exact source functions and files. Every task that introduces new logic carries the real code.

**Type consistency.** `task_row()` from Task 5 is what Tasks 6, 7, and 8 return. `EMPTY_TASKS()` supplies the same five buckets everywhere. `check() -> tuple[bool, str]` is used identically by providers and the wizard. `providers.reset()` is defined in Task 8 and used by Task 8's tests and Task 11's wizard. `state.today()` stays a function so Task 9's tests can monkeypatch it.

**Known risk.** Task 8 touches live code paths the app depends on daily. Its step 7 runs the real app against the real Google task list before committing, so a regression surfaces there rather than the next morning.
