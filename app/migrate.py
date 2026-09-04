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


def _is_default_home() -> bool:
    """Whether HERD_HOME is where an unconfigured install would put it.

    OLD_DAILY is one machine's absolute path, so a clone anywhere on that
    machine used to offer to move those day files, and run() deletes the
    originals once copied. A scratch install pointed at a temporary
    HERD_HOME has no business touching them.
    """
    return paths.home() == Path(paths.DEFAULT_HOME).expanduser()


def find_old(repo_root: Path | None = None, old_daily: Path | None = None) -> dict:
    """Old-layout data worth moving, keyed by what it is.

    The herd and picks are looked for beside the code, so they follow the
    clone. The day files live at a fixed path instead, and are only offered
    when this is the install that owns them.
    """
    explicit_root = repo_root is not None
    root = repo_root or Path(__file__).parent.parent
    explicit = old_daily is not None
    daily = old_daily if explicit else OLD_DAILY

    # A repo-root herd belongs to whoever installed here. run() unlinks the
    # original once copied, so a scratch HERD_HOME must not be offered it.
    owns = explicit_root or _is_default_home()

    found = {}
    if owns and (root / "herd.json").exists() and not paths.herd_file().exists():
        found["herd"] = root / "herd.json"
    if owns and (root / "picks.json").exists() and not paths.picks_file().exists():
        found["picks"] = root / "picks.json"
    if (explicit or _is_default_home()) and daily.is_dir() and any(daily.glob("*.md")):
        found["daily"] = daily
    return found


def _move_json(src: Path, dst: Path) -> tuple[bool, int]:
    """Copy a JSON file, confirm it parses, then drop the original.

    Returns whether the move happened and, for a herd, how many cats came
    with it. Success is reported separately from the count, because a valid
    picks file legitimately has no cats and would otherwise look like a
    failed copy.
    """
    try:
        parsed = json.loads(src.read_text())
    except json.JSONDecodeError:
        return False, 0
    dst.write_text(json.dumps(parsed, indent=2))
    if json.loads(dst.read_text()) != parsed:
        return False, 0
    src.unlink()
    return True, sum(len(v) for v in parsed.get("days", {}).values())


def run(sources: dict) -> dict:
    """Move what find_old turned up. Returns what moved."""
    paths.ensure()
    result = {"cats": 0, "picks": 0, "daily": 0}

    if "herd" in sources:
        _, result["cats"] = _move_json(sources["herd"], paths.herd_file())

    if "picks" in sources and not paths.picks_file().exists():
        moved, _ = _move_json(sources["picks"], paths.picks_file())
        result["picks"] = 1 if moved else 0

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
