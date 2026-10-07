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

APP_DIRS = (Path("/Applications"), Path.home() / "Applications")

# App names the scan knows something about. Channels do not change the config
# (the skill reads them, not the dashboard) but naming them tells a new user
# what the sweep will and will not reach.
UNSUPPORTED_TASK_APPS = {
    "things": "Things", "things3": "Things", "reminders": "Apple Reminders",
    "ticktick": "TickTick", "omnifocus": "OmniFocus",
}
CHANNEL_APPS = {
    "slack": "Slack", "notion": "Notion", "grain": "Grain", "fathom": "Fathom",
    "linear": "Linear", "superhuman": "Superhuman", "outlook": "Outlook",
}


def _installed_apps() -> set[str]:
    found: set[str] = set()
    for directory in APP_DIRS:
        if not directory.is_dir():
            continue
        for entry in directory.glob("*.app"):
            found.add(entry.stem.lower())
    return found


def _gws_ready() -> bool:
    proc = subprocess.run(["gws", "auth", "status"], capture_output=True, timeout=30)
    return proc.returncode == 0


def _scan_device(output_fn) -> dict:
    """Look at what is installed and suggest which providers to configure.

    Detection is honest about its limits: a Google account used entirely in a
    browser leaves no app to find, so gws authentication is the only real
    signal for it, and an installed app says nothing about whether the person
    actually uses it. Recommendations are defaults for the menus, not
    decisions made for them.
    """
    apps = _installed_apps()
    try:
        gws = _gws_ready()
    except Exception:
        gws = False

    task_default = ""
    mail_default = ""

    output_fn("\nWhat I found:\n")
    if "todoist" in apps:
        output_fn("  - Todoist is installed, and it is a supported task provider\n")
        task_default = "todoist"
    elif gws:
        output_fn(
            "  - The gws CLI is authenticated, so Google Tasks works as-is\n"
        )
        task_default = "google"
    unsupported = sorted(UNSUPPORTED_TASK_APPS[a] for a in apps if a in UNSUPPORTED_TASK_APPS)
    if unsupported:
        output_fn(
            f"  - {', '.join(unsupported)} installed, but there is no provider "
            "for it. Task choices are Google Tasks, Todoist, or a local "
            "markdown file\n"
        )

    if gws:
        output_fn(
            "  - Gmail works through the same gws CLI. Other mail providers "
            "are not supported\n"
        )
        mail_default = "gmail"

    channels = sorted(CHANNEL_APPS[a] for a in apps if a in CHANNEL_APPS)
    if channels:
        output_fn(
            f"  - Also installed: {', '.join(channels)}. The dashboard only "
            "configures tasks and mail, but the optional skill sweep reads "
            "Slack, mail, Notion and call recordings, so these name what it "
            "can see\n"
        )

    if not task_default:
        output_fn(
            "  - Nothing detected that points at a task provider. The choices "
            "are Google Tasks, Todoist, or a local markdown file\n"
        )
    output_fn("")

    return {"task_default": task_default, "mail_default": mail_default}


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


def run(input_fn=input, output_fn=print, scan_fn=_scan_device) -> Path:
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

    # The interview: what do you actually use? The scan offers device evidence
    # first; the plain question covers everything a scan cannot see, like a
    # Google account used only in a browser.
    scan: dict = {}
    if _ask(
        input_fn, output_fn,
        "Want me to look at what is installed on this machine and suggest a "
        "setup? (y/n)",
        "n",
    ).lower().startswith("y"):
        scan = scan_fn(output_fn)

    # Task provider: verify before persisting, re-ask on failure rather than
    # writing a config that cannot actually reach the account it names.
    task_provider = ""
    task_extra: dict = {}
    while True:
        output_fn(
            "What do you use for tasks?\n"
            "  1. Google Tasks\n  2. Todoist\n  3. Local markdown file\n"
        )
        default_task = {"google": "1", "todoist": "2"}.get(scan.get("task_default", ""), "1")
        choice = _ask(input_fn, output_fn, "Choice", default_task)
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
        output_fn(
            "What do you use for email? Mail support is Gmail only, read "
            "through the gws CLI.\n  1. Gmail\n  2. None\n"
        )
        default_mail = {"gmail": "1"}.get(scan.get("mail_default", ""), "2")
        choice = _ask(input_fn, output_fn, "Choice", default_mail)
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
