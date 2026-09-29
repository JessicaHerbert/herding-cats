"""The sweep run log.

One JSON line per run in `runs.jsonl`, append only. This answers the
questions `sweep.json` cannot, because that file holds only the latest run
and is overwritten each time: how often does the schedule actually fire, what
does it cost across a week, and are the gatherers really landing on haiku.

Cost and the per-model split exist only on the CLI's final result event and
appear nowhere in the session transcript, so a run not recorded here can
never be priced afterwards.

Append only, and never rewritten in place. A run that crashes mid-write costs
one malformed line, which `read()` skips, rather than a truncated file.
"""

import json
import time

from . import paths, state

# Keep roughly a quarter of hourly weekday runs. Ten a day, five days a week,
# so this is about three months, which is enough to see a monthly trend
# without the file needing management.
MAX_LINES = 650


def record(
    *,
    trigger: str,
    logged: int,
    cost_usd: float | None = None,
    duration_ms: int | None = None,
    models: dict | None = None,
    error: str = "",
) -> dict:
    """Append one run. Returns the row written.

    `trigger` is "schedule" or "button", which is the whole reason the log is
    worth keeping: an unattended run and one she pressed have different bars
    and different costs, and telling them apart later is impossible without
    recording it at the time.
    """
    row = {
        "at": time.time(),
        "day": state.working_day(),
        "clock": state.today().strftime("%H:%M"),
        "trigger": trigger,
        "logged": logged,
        "cost_usd": round(cost_usd, 4) if isinstance(cost_usd, (int, float)) else None,
        "duration_ms": duration_ms,
        "models": {
            # Canonical short names. The raw keys carry a version suffix that
            # changes under you, so a chart grouped on the full id silently
            # splits into two series the day a model rolls.
            _short(name): {
                "cost_usd": round(u["cost_usd"], 4)
                if isinstance(u.get("cost_usd"), (int, float))
                else None,
                "input": u.get("input"),
                "output": u.get("output"),
            }
            for name, u in (models or {}).items()
        },
        "error": error[:200],
    }

    path = paths.runs_file()
    paths.ensure()
    with path.open("a") as fh:
        fh.write(json.dumps(row) + "\n")

    _trim(path)
    return row


def _short(model: str) -> str:
    """`claude-haiku-4-5-20251001` and `claude-opus-5[1m]` to `haiku`, `opus`."""
    for family in ("haiku", "sonnet", "opus"):
        if family in model:
            return family
    return model


def _trim(path) -> None:
    """Keep the file bounded, dropping the oldest lines."""
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return
    if len(lines) <= MAX_LINES:
        return
    path.write_text("\n".join(lines[-MAX_LINES:]) + "\n")


def read(limit: int = 100) -> list[dict]:
    """The most recent runs, newest first. Malformed lines are skipped."""
    path = paths.runs_file()
    if not path.exists():
        return []

    rows = []
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return []

    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            # A half-written line from an interrupted run. One bad row must
            # not take the whole panel down.
            continue
    rows.reverse()
    return rows


def summary(rows: list[dict] | None = None) -> dict:
    """Totals for today and for the trailing week.

    Cost is summed only over runs that reported one. A run with a null cost
    is counted in `runs` but not in `cost_usd`, so the average is over what
    was actually measured rather than treating a missing value as zero.
    """
    rows = read(MAX_LINES) if rows is None else rows
    today = state.working_day()

    def totals(subset):
        priced = [r for r in subset if isinstance(r.get("cost_usd"), (int, float))]
        by_model: dict[str, float] = {}
        for r in subset:
            for name, u in (r.get("models") or {}).items():
                c = u.get("cost_usd")
                if isinstance(c, (int, float)):
                    by_model[name] = round(by_model.get(name, 0) + c, 4)
        return {
            "runs": len(subset),
            "priced": len(priced),
            "cats": sum(r.get("logged") or 0 for r in subset),
            "cost_usd": round(sum(r["cost_usd"] for r in priced), 4),
            "by_model": by_model,
        }

    week_start = time.time() - 7 * 86400
    return {
        "today": totals([r for r in rows if r.get("day") == today]),
        "week": totals([r for r in rows if (r.get("at") or 0) >= week_start]),
    }
