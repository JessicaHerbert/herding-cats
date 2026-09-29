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


def runs_file() -> Path:
    """The sweep run log: one JSON line per run, append only.

    Separate from sweep.json, which holds only the most recent run and is
    overwritten each time. This is the history: when a sweep ran, what it
    cost, which models it used and how many cats it logged.
    """
    return home() / "runs.jsonl"


def daily_dir() -> Path:
    return home() / "daily"


def ensure() -> Path:
    """Create the tree if it is not there yet. Returns the root."""
    root = home()
    root.mkdir(parents=True, exist_ok=True)
    daily_dir().mkdir(parents=True, exist_ok=True)
    return root
