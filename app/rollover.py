"""Create today's day file on first read of the day.

Two previous attempts at a daily log died because they needed someone to go
somewhere and start one. This runs on first read of the day, so the file
exists before you look for it.
"""

from datetime import datetime

from . import state

TEMPLATE = """# {date}, {weekday}

## On the list

## Decisions

## Open threads

## Notes
"""


def ensure_today() -> dict:
    """Make sure today's day file exists. Returns what it did."""
    path = state.day_file_path()
    if path.exists():
        return {"created": False}

    today = state.working_day()
    day = datetime.strptime(today, "%Y-%m-%d")
    body = TEMPLATE.format(date=today, weekday=day.strftime("%A"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return {"created": True}
