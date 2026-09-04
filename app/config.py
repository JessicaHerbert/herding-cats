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
