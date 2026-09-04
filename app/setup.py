"""First-run setup wizard.

Walks a new install through picking a task provider and a mail provider,
verifies each choice with its own check() before anything is written, offers
to bring over data from the old fixed-path layout, then writes config.toml.

input_fn and output_fn are injected so the whole flow is testable without a
real terminal: pass an iterator's __next__ (via a small lambda) for input_fn
and a list's append for output_fn.
"""

import json
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config, migrate, paths

TASK_PROVIDER_MENU = {"1": "google", "2": "todoist", "3": "localfile"}
MAIL_PROVIDER_MENU = {"1": "gmail", "2": "none"}


def needed() -> bool:
    return not config.exists()


def _ask(input_fn, output_fn, prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    output_fn(f"{prompt}{suffix}: ")
    answer = (input_fn() or "").strip()
    return answer if answer else default


def write_config(cfg: dict) -> Path:
    """Emit flat TOML by hand. Empty values are skipped so a config for one
    provider carries no stray keys belonging to another."""
    paths.ensure()

    lines = []
    for section in ("general", "tasks", "mail"):
        lines.append(f"[{section}]")
        for key, value in cfg.get(section, {}).items():
            if value == "" or value is None:
                continue
            if isinstance(value, bool):
                lines.append(f"{key} = {'true' if value else 'false'}")
            elif isinstance(value, int):
                lines.append(f"{key} = {value}")
            else:
                escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'{key} = "{escaped}"')
        lines.append("")

    target = paths.config_file()
    target.write_text("\n".join(lines).rstrip() + "\n")
    return target


def _gws_tasklists() -> list[dict]:
    proc = subprocess.run(
        ["gws", "tasks", "tasklists", "list"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[:300] or "gws failed")
    data = json.loads(proc.stdout)
    return data.get("items", [])


def _choose_google(input_fn, output_fn) -> dict:
    try:
        tasklists = _gws_tasklists()
    except Exception:
        output_fn(
            "Could not list Google task lists. The gws CLI may be missing "
            "or not authenticated.\n"
        )
        return {}
    if not tasklists:
        output_fn("No Google task lists found.\n")
        return {}

    output_fn("Choose a task list:\n")
    for i, item in enumerate(tasklists, start=1):
        output_fn(f"  {i}. {item.get('title', '(untitled)')}\n")
    choice = _ask(input_fn, output_fn, "Task list number", "1")
    try:
        index = int(choice) - 1
        picked = tasklists[index]
    except (ValueError, IndexError):
        picked = tasklists[0]
    return {"tasklist": picked.get("id", "")}


def _choose_todoist(input_fn, output_fn) -> dict:
    token = _ask(input_fn, output_fn, "Todoist API token")
    return {"token": token}


def _choose_localfile(input_fn, output_fn) -> dict:
    from .providers.localfile import HEADER

    default_path = str(paths.home() / "tasks.md")
    path = _ask(input_fn, output_fn, "Path to your tasks markdown file", default_path)
    file_path = Path(path).expanduser()
    if not file_path.exists():
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(HEADER)
        output_fn(f"Created {file_path}\n")
    return {"path": str(file_path)}


def _make_task_provider(which: str, extra: dict):
    if which == "google":
        from .providers.google_tasks import GoogleTasksProvider

        return GoogleTasksProvider(extra.get("tasklist", ""))
    if which == "todoist":
        from .providers.todoist import TodoistProvider

        return TodoistProvider(extra.get("token", ""))
    from .providers.localfile import LocalFileProvider

    return LocalFileProvider(extra.get("path", ""))


def _make_mail_provider(which: str, address: str):
    if which == "gmail":
        from .providers.gmail import GmailProvider

        return GmailProvider(address)
    return None


def run(input_fn=input, output_fn=print) -> Path:
    output_fn("Herding Cats setup\n")

    while True:
        timezone = _ask(input_fn, output_fn, "Timezone", config._system_timezone())
        try:
            ZoneInfo(timezone)
            break
        except Exception:
            # Every other prompt verifies before persisting. Without this the
            # wizard writes an unloadable zone, prints success, and the app
            # then refuses to start with a ConfigError.
            output_fn(f"  {timezone!r} is not a zone name. Try one like America/New_York.")
    day_starts_raw = _ask(input_fn, output_fn, "What hour does your day start at (0-23)", "6")
    try:
        day_starts_at = int(day_starts_raw)
    except ValueError:
        day_starts_at = 6

    # Task provider: verify before persisting, re-ask on failure rather than
    # writing a config that cannot actually reach the account it names.
    task_provider = ""
    task_extra: dict = {}
    while True:
        output_fn("Task provider:\n  1. Google Tasks\n  2. Todoist\n  3. Local markdown file\n")
        choice = _ask(input_fn, output_fn, "Choice", "1")
        task_provider = TASK_PROVIDER_MENU.get(choice, "google")

        if task_provider == "google":
            task_extra = _choose_google(input_fn, output_fn)
        elif task_provider == "todoist":
            task_extra = _choose_todoist(input_fn, output_fn)
        else:
            task_extra = _choose_localfile(input_fn, output_fn)

        provider = _make_task_provider(task_provider, task_extra)
        ok, message = provider.check()
        if ok:
            break
        output_fn(f"That did not work: {message}\n")

    # Mail provider: same verify-before-persist rule.
    mail_provider = ""
    mail_address = ""
    while True:
        output_fn("Mail provider:\n  1. Gmail\n  2. None\n")
        choice = _ask(input_fn, output_fn, "Choice", "2")
        mail_provider = MAIL_PROVIDER_MENU.get(choice, "none")

        if mail_provider == "gmail":
            mail_address = _ask(input_fn, output_fn, "Your Gmail address")
        else:
            mail_address = ""

        provider = _make_mail_provider(mail_provider, mail_address)
        if provider is None:
            break
        ok, message = provider.check()
        if ok:
            break
        output_fn(f"That did not work: {message}\n")

    found = migrate.find_old()
    if found:
        answer = _ask(
            input_fn, output_fn,
            "Found existing herd data from an earlier layout. Move it in now? (y/n)",
            "n",
        )
        if answer.lower().startswith("y"):
            moved = migrate.run(found)
            output_fn(
                f"Moved {moved['cats']} cats, {moved['picks']} picks file, "
                f"{moved['daily']} daily notes.\n"
            )

    cfg = {
        "general": {"timezone": timezone, "day_starts_at": day_starts_at},
        "tasks": {
            "provider": task_provider,
            "tasklist": task_extra.get("tasklist", ""),
            "token": task_extra.get("token", ""),
            "path": task_extra.get("path", ""),
        },
        "mail": {"provider": mail_provider, "address": mail_address},
    }
    target = write_config(cfg)
    output_fn(f"Wrote {target}\n")
    return target


if __name__ == "__main__":
    run()
