"""Task and calendar reads through the provider seam, plus day-file access."""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import paths


def tz() -> ZoneInfo:
    """The configured zone.

    config.reload() already refuses a zone that will not load, so there is
    nothing left to swallow here. The previous fallback to UTC turned a
    four-hour error in the day boundary into something silent.
    """
    from . import config

    return ZoneInfo(config.load()["general"]["timezone"])


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


def tasks() -> dict:
    from . import providers

    return providers.tasks().list_tasks()


def calendar() -> dict:
    from . import providers

    cal = providers.calendar_or_none()
    return cal.today() if cal else {"events": [], "collisions": []}


def day_file_path(date: str | None = None) -> Path:
    """The day file, with its directory guaranteed to exist.

    Callers write to this path directly in nine places. Creating the parent
    here covers all of them, where a fresh HERD_HOME otherwise fails on the
    first append with a bare FileNotFoundError.
    """
    daily = paths.daily_dir()
    daily.mkdir(parents=True, exist_ok=True)
    return daily / f"{date or working_day()}.md"


def day_file() -> str:
    path = day_file_path()
    return path.read_text() if path.exists() else ""


def append_done(text: str) -> None:
    """Add a line to the day file's On the list section as already done."""
    path = day_file_path()
    stamp = today().strftime("%H:%M")
    line = f"- [x] {text} ({stamp})\n"
    if not path.exists():
        day = datetime.strptime(working_day(), "%Y-%m-%d")
        path.write_text(
            f"# {day.strftime('%Y-%m-%d, %A')}\n\n## On the list\n{line}\n"
            "## Decisions\n\n## Open threads\n\n## Notes\n"
        )
        return
    body = path.read_text()
    # Anchor on whichever section comes FIRST after "On the list", not on
    # "## Decisions" specifically, so an inserted "## For Claude" section
    # still keeps completions out of it.
    markers = [m for m in ("## Decisions", "## Open threads",
                           "## Notes", "## For Claude") if m in body]
    marker = min(markers, key=body.index) if markers else ""
    if marker:
        head, _, tail = body.partition(marker)
        path.write_text(f"{head.rstrip()}\n{line}\n{marker}{tail}")
    else:
        path.write_text(body.rstrip() + "\n" + line)


def append_note(text: str, about: str = "") -> None:
    """Drop a note into the day file for Claude Code to pick up.

    Notes land in their own "## For Claude" section rather than in Notes, so
    the ones written at the dashboard asking for something are separable from
    the ones Claude wrote down as reference.
    """
    path = day_file_path()
    stamp = today().strftime("%H:%M")
    line = f"- [ ] {stamp}" + (f" **{about}** - " if about else " ") + text + "\n"
    section = "## For Claude"

    if not path.exists():
        day = datetime.strptime(working_day(), "%Y-%m-%d")
        path.write_text(
            f"# {day.strftime('%Y-%m-%d, %A')}\n\n## On the list\n\n"
            f"{section}\n{line}\n## Decisions\n\n## Open threads\n\n## Notes\n"
        )
        return

    body = path.read_text()
    if section in body:
        head, _, tail = body.partition(section)
        rest = tail.split("\n## ", 1)
        entries = rest[0].rstrip("\n")
        remainder = ("\n## " + rest[1]) if len(rest) > 1 else ""
        path.write_text(f"{head}{section}{entries}\n{line}{remainder}")
    elif "## Decisions" in body:
        head, _, tail = body.partition("## Decisions")
        path.write_text(f"{head.rstrip()}\n\n{section}\n{line}\n## Decisions{tail}")
    else:
        path.write_text(body.rstrip() + f"\n\n{section}\n{line}")


def uncomplete_task(task_id: str) -> dict:
    from . import providers

    return providers.tasks().uncomplete(task_id)


def remove_done(text: str) -> bool:
    """Take a completed line back out of the day file.

    Undo used to only drop the cat from herd.json, but sync_day_file re-adds
    any `- [x]` line on the next state read, so an undone item came straight
    back. Matched loosely, since the line carries a timestamp the caller has
    no reason to know.
    """
    import re

    path = day_file_path()
    if not path.exists():
        return False

    want = re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())
    want = " ".join(w for w in want.split() if len(w) > 2)[:60]
    if not want:
        return False

    kept, dropped = [], False
    for line in path.read_text().splitlines():
        m = re.match(r"^\s*-\s*\[x\]\s+(.+?)\s*$", line, re.I)
        if m:
            got = re.sub(r"[^a-z0-9 ]+", " ", m.group(1).lower())
            got = " ".join(w for w in got.split() if len(w) > 2)[:60]
            if got == want:
                dropped = True
                continue
        kept.append(line)

    if dropped:
        path.write_text("\n".join(kept) + "\n")
    return dropped


def complete_task(task_id: str) -> dict:
    from . import providers

    return providers.tasks().complete(task_id)


def create_task(title: str, notes: str = "", due: str | None = None) -> dict:
    from . import providers

    return providers.tasks().create(title, notes, due)
