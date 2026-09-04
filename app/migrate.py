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
