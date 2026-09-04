"""The herd. One cat per completed task, kept on disk so it survives restarts."""

import json
from pathlib import Path

from . import coats, names, state

HERD = Path(__file__).parent.parent / "herd.json"

# Rarer cats sit further down the list. Index = how many cats you had when
# this one was earned, so the herd visibly changes character as it grows.
BREEDS = [
    ("🐱", "tabby"),
    ("🐈", "shorthair"),
    ("🐈‍⬛", "void"),
    ("😼", "smug"),
    ("😻", "delighted"),
    ("🦁", "lion"),
    ("🐯", "tiger"),
]

MILESTONES = {
    1: "First cat of the day.",
    3: "Three cats. A small herd.",
    5: "Five cats. They are starting to follow you.",
    10: "Ten cats. This is now a situation.",
    15: "Fifteen. You have lost control and that is fine.",
    25: "Twenty-five cats. Genuinely a lot of cats.",
}


def _key(title: str) -> str:
    """Loose match, so the same work logged in two places earns one cat.

    A Google Task titled "Answer SAF" and a day-file line reading
    "Answer SAF (08:30 block)" are the same thing.
    """
    import re

    t = re.sub(r"\(.*?\)", " ", (title or "").lower())
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    words = [w for w in t.split() if len(w) > 2]
    return " ".join(words[:5])


def _load() -> dict:
    if not HERD.exists():
        return {"days": {}, "total": 0}
    try:
        return json.loads(HERD.read_text())
    except json.JSONDecodeError:
        return {"days": {}, "total": 0}


def _save(data: dict) -> None:
    HERD.write_text(json.dumps(data, indent=2))


def _breed(total: int) -> tuple[str, str]:
    """Pick a breed from the running total, so rarer ones show up later."""
    return BREEDS[min(total // 4, len(BREEDS) - 1)]


def _recent_keys(data: dict, today: str, back: int = 14) -> set:
    """Cat keys already awarded on the days just before today.

    Dedup used to be scoped to the current day only, so anything that leaked
    across the 6am boundary earned a second cat for work already counted.
    """
    from datetime import datetime, timedelta

    day = datetime.strptime(today, "%Y-%m-%d")
    keys = set()
    for n in range(1, back + 1):
        prior = (day - timedelta(days=n)).strftime("%Y-%m-%d")
        for c in data["days"].get(prior, []):
            keys.add(_key(c["for"]))
    return keys


def sync_day_file() -> dict:
    """Award a cat for every checked item in today's day file.

    The day file carries work that never was a Google Task, which on
    2026-09-01 was most of what actually got done. Keyed on the item text so
    re-running does not duplicate cats.
    """
    import re

    data = _load()
    today = state.working_day()
    day = data["days"].setdefault(today, [])
    seen = {_key(c["for"]) for c in day} | _recent_keys(data, today)

    body = state.day_file()
    if not body:
        return {"added": 0}

    section = body.split("## Decisions")[0]
    added = 0
    for line in section.splitlines():
        m = re.match(r"^\s*-\s*\[x\]\s+(.+?)\s*$", line, re.IGNORECASE)
        if not m:
            continue
        raw = m.group(1)
        # append_done stamps the time into the text as "(HH:MM)", so pull it
        # back out rather than dropping it with the rest of the parentheticals.
        stamped = re.search(r"\((\d{2}:\d{2})\)\s*$", raw)
        at = stamped.group(1) if stamped else ""
        title = re.sub(r"\s*\(\d{2}:\d{2}\)\s*$", "", raw).strip()
        title = re.sub(r"\s*[-(]\s*(completed|contract sent).*$", "", title, flags=re.I).strip()
        title = re.sub(r"\s*\(\d{2}:\d{2} block\)\s*$", "", title).strip()
        if not title or _key(title) in seen:
            continue
        data["total"] += 1
        emoji, breed = _breed(data["total"])
        coat = coats.for_position(len(day), title)
        day.append({
            "emoji": emoji, "breed": breed, "for": title,
            "at": at, "source": "day file",
            "coat": coat["name"], "rare": coat.get("rare"),
            "name": names.for_cat(title, coat.get("rare"), coats.hash_text(title)),
            **coats.traits_for(title),
        })
        seen.add(_key(title))
        added += 1

    if added:
        _save(data)
    return {"added": added, "today": len(day), "total": data["total"]}


def earn(task_title: str) -> dict:
    data = _load()
    today = state.working_day()
    day = data["days"].setdefault(today, [])

    # One cat per piece of work. A double-click on the same task used to award
    # two, which makes the pile a count of clicks rather than of work done.
    if _key(task_title) in {_key(c["for"]) for c in day}:
        return {
            "cat": None,
            "duplicate": True,
            "today": len(day),
            "total": data["total"],
            "milestone": None,
        }

    data["total"] += 1
    emoji, breed = _breed(data["total"])
    coat = coats.for_position(len(day), task_title)
    traits = coats.traits_for(task_title)
    name = names.for_cat(task_title, coat.get("rare"), coats.hash_text(task_title))
    cat = {
        "emoji": emoji,
        "breed": breed,
        "for": task_title,
        "at": state.today().strftime("%H:%M"),
        "coat": coat["name"],
        "rare": coat.get("rare"),
        "name": name,
        **traits,
    }
    day.append(cat)
    _save(data)

    return {
        "cat": cat,
        "today": len(day),
        "total": data["total"],
        "milestone": MILESTONES.get(len(day)),
    }


def sync_completed(done_today: list[dict]) -> int:
    """Award cats for tasks completed outside the dashboard.

    Google Tasks is the source of truth, so a task checked off on the phone or
    in the web UI still counts. Deduped on the same loose key as everything
    else, so this cannot double up with a dashboard completion.
    """
    if not done_today:
        return 0

    data = _load()
    today = state.working_day()
    day = data["days"].setdefault(today, [])
    seen = {_key(c["for"]) for c in day}

    added = 0
    for task in done_today:
        title = (task.get("title") or "").strip()
        if not title or _key(title) in seen:
            continue
        data["total"] += 1
        emoji, breed = _breed(data["total"])
        stamp = (task.get("completed") or "")[11:16]
        coat = coats.for_position(len(day), title)
        day.append({
            "emoji": emoji, "breed": breed, "for": title,
            "at": stamp, "source": "google tasks",
            "coat": coat["name"], "rare": coat.get("rare"),
            "name": names.for_cat(title, coat.get("rare"), coats.hash_text(title)),
            **coats.traits_for(title),
        })
        seen.add(_key(title))
        added += 1

    if added:
        _save(data)
    return added


def unearn(task_title: str) -> dict:
    """Take back the cat for a task, for when it was checked off by accident."""
    data = _load()
    today = state.working_day()
    day = data["days"].get(today, [])

    want = _key(task_title)
    for i in range(len(day) - 1, -1, -1):
        if _key(day[i]["for"]) == want:
            day.pop(i)
            data["total"] = max(0, data["total"] - 1)
            # Removing from the middle shifts every later cat back one, and the
            # every-tenth gold is positional, so the stored coats no longer
            # match where the cats sit. Re-derive the tail.
            for pos in range(i, len(day)):
                coat = coats.for_position(pos, day[pos]["for"])
                day[pos]["coat"] = coat["name"]
                day[pos]["rare"] = coat.get("rare")
                day[pos]["name"] = names.for_cat(
                    day[pos]["for"], coat.get("rare"), coats.hash_text(day[pos]["for"])
                )
            if not day:
                data["days"].pop(today, None)
            _save(data)
            # Also drop the day-file line, or sync_day_file puts the cat back.
            state.remove_done(task_title)
            return {"removed": True, "today": len(day), "total": data["total"]}

    return {"removed": False, "today": len(day), "total": data["total"]}


def history(limit: int = 30) -> dict:
    """Every day on record, newest first, with coat and breed tallies.

    The whole herd has always been stored; only `today` was ever exposed, so
    the history existed and nothing could read it.
    """
    data = _load()
    days = []
    coat_tally: dict[str, int] = {}
    rare_tally: dict[str, int] = {}
    breed_tally: dict[str, int] = {}
    trait_tally = {k: 0 for k in
                   ("whiskers", "accessories", "head", "droop",
                    "bigEyes", "bigEars", "tabby", "pixel")}

    for day in sorted(data["days"], reverse=True):
        cats = data["days"][day]
        for c in cats:
            if c.get("coat"):
                coat_tally[c["coat"]] = coat_tally.get(c["coat"], 0) + 1
            if c.get("rare"):
                rare_tally[c["rare"]] = rare_tally.get(c["rare"], 0) + 1
            breed_tally[c["breed"]] = breed_tally.get(c["breed"], 0) + 1
            for t in trait_tally:
                # `head` is a string; the countable case is the rarer shape.
                got = c.get(t)
                if (got == "triangular") if t == "head" else bool(got):
                    trait_tally[t] += 1
        days.append({
            "day": day,
            "count": len(cats),
            "rare": sum(1 for c in cats if c.get("rare")),
            "cats": cats,
        })

    counts = [d["count"] for d in days] or [0]
    return {
        "days": days[:limit],
        "total": data["total"],
        "days_kept": len(data["days"]),
        "best": max(counts),
        "average": round(sum(counts) / len(counts), 1),
        "coats": dict(sorted(coat_tally.items(), key=lambda kv: -kv[1])),
        "rares": rare_tally,
        "breeds": breed_tally,
        "traits": trait_tally,
        "streak": _streak(data["days"]),
    }


def _streak(days: dict) -> int:
    """Consecutive days with at least one cat, counting back from the latest."""
    from datetime import datetime, timedelta

    if not days:
        return 0
    dates = sorted(days, reverse=True)
    run = 1
    cursor = datetime.strptime(dates[0], "%Y-%m-%d")
    for d in dates[1:]:
        prev = datetime.strptime(d, "%Y-%m-%d")
        if (cursor - prev).days == 1:
            run += 1
            cursor = prev
        else:
            break
    return run


def herd() -> dict:
    data = _load()
    today = state.working_day()
    return {
        "today": data["days"].get(today, []),
        "total": data["total"],
        "days_kept": len(data["days"]),
    }
