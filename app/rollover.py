"""Create today's day file, carrying forward what is still unresolved.

Two previous attempts at a daily log died because they needed Jess to go
somewhere and start one. This runs on first read of the day, so the file
exists before she looks for it, and the watchlist survives the boundary
instead of starting empty every morning.
"""

import re
from datetime import datetime, timedelta

from . import state, watch

TEMPLATE = """# {date}, {weekday}

## On the list

## Watching
{watching}
## Decisions

## Open threads

## Notes
"""

RESOLVED = ("ok",)

# A "- [x]" line is finished work, not something still being watched. Carrying
# it into the new day made sync_day_file re-award a cat for every item of the
# night before, because that dedup only ever looks at the current day.
DONE_ITEM = re.compile(r"^\s*[-*]\s*\[x\]", re.IGNORECASE)


def _previous_day_file() -> tuple[str, str] | None:
    """The most recent day file before today, within a fortnight."""
    today = state.working_day()
    day = datetime.strptime(today, "%Y-%m-%d")
    for back in range(1, 15):
        candidate = (day - timedelta(days=back)).strftime("%Y-%m-%d")
        path = state.day_file_path(candidate)
        if path.exists():
            return candidate, path.read_text()
    return None


def _carry_forward(previous: str) -> list[str]:
    """Unresolved Watching lines from the previous day file, verbatim.

    Resolved items are dropped rather than carried, so the list shrinks on its
    own instead of becoming a graveyard nobody reads.
    """
    lines = previous.splitlines()
    start = None
    for i, line in enumerate(lines):
        if watch.HEADING.match(line.strip()):
            start = i + 1
            break
    if start is None:
        return []

    kept = []
    for line in lines[start:]:
        if watch.NEXT_HEADING.match(line):
            break
        if DONE_ITEM.match(line):
            continue
        m = watch.ITEM.match(line)
        if not m:
            continue
        parts = [p.strip() for p in m.group(1).split("|")]
        found = parts[2] if len(parts) > 2 else ""
        if watch._classify(found) in RESOLVED:
            continue
        kept.append(line.rstrip())
    return kept


def ensure_today() -> dict:
    """Make sure today's day file exists. Returns what it did."""
    path = state.day_file_path()
    if path.exists():
        return {"created": False, "carried": 0}

    today = state.working_day()
    day = datetime.strptime(today, "%Y-%m-%d")

    carried: list[str] = []
    prev = _previous_day_file()
    if prev:
        carried = _carry_forward(prev[1])

    body = TEMPLATE.format(
        date=today,
        weekday=day.strftime("%A"),
        watching=("\n".join(carried) + "\n") if carried else "",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return {"created": True, "carried": len(carried), "from": prev[0] if prev else None}
