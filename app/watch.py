"""The watchlist, parsed out of the day file.

Claude Code owns this section. The dashboard only reads it, so nothing here
triggers a tool call or costs tokens in the background.

Expected shape in the day file:

    ## Watching
    - [PLUGIN-377](https://...) missing Request Source | 23:12 | still open
    - Marketing Slack app | 12:48 | still firing
    - GoLive decision | waiting on Alexia

The pipe-delimited fields after the label are optional: the second is when it
was last checked, the third is what was found.
"""

import re

from . import state

HEADING = re.compile(r"^##+\s*watch(ing|list)?\s*$", re.IGNORECASE)
NEXT_HEADING = re.compile(r"^##+\s+")
ITEM = re.compile(r"^\s*[-*]\s+(.*)$")
LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")

# Words that mean the thing is still wrong, so the dashboard can color it.
BAD = ("still", "not ", "no ", "fail", "broken", "empty", "missing", "open", "blocked")
GOOD = ("fixed", "done", "resolved", "closed", "set", "cleared", "landed")


def _classify(found: str) -> str:
    """Guess from wording, but let an explicit marker override.

    Word matching alone is unreliable: "phase set, both dates still empty" hits
    both lists. A leading (ok) / (bad) marker is the escape hatch when the
    wording is genuinely mixed.
    """
    low = found.lower().strip()
    if low.startswith(("(ok)", "[ok]")):
        return "ok"
    if low.startswith(("(bad)", "[bad]", "(open)")):
        return "bad"

    # A "still" anywhere means unresolved regardless of what else is in there.
    if "still" in low or "not yet" in low:
        return "bad"
    if any(w in low for w in GOOD):
        return "ok"
    if any(w in low for w in BAD):
        return "bad"
    return "neutral"


def watching() -> list[dict]:
    body = state.day_file()
    if not body:
        return []

    lines = body.splitlines()
    start = None
    for i, line in enumerate(lines):
        if HEADING.match(line.strip()):
            start = i + 1
            break
    if start is None:
        return []

    items = []
    for line in lines[start:]:
        if NEXT_HEADING.match(line):
            break
        m = ITEM.match(line)
        if not m:
            continue

        parts = [p.strip() for p in m.group(1).split("|")]
        label = parts[0]
        checked = parts[1] if len(parts) > 1 else ""
        found = parts[2] if len(parts) > 2 else ""

        link = LINK.search(label)
        items.append({
            "label": LINK.sub(r"\1", label).strip(),
            "url": link.group(2) if link else "",
            "checked": checked,
            "found": found,
            "status": _classify(found or checked),
        })

    return items
