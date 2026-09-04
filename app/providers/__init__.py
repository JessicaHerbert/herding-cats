"""Pick the configured backend and hand it to the rest of the app."""

from .. import config

_tasks = None
_mail = None
_calendar = None
_resolved = False


def reset() -> None:
    """Drop the cache. Used by the wizard and by tests."""
    global _tasks, _mail, _calendar, _resolved
    _tasks = _mail = _calendar = None
    _resolved = False


def _resolve() -> None:
    global _tasks, _mail, _calendar, _resolved
    if _resolved:
        return
    cfg = config.load()

    which = cfg["tasks"]["provider"]
    if which == "localfile":
        from .localfile import LocalFileProvider

        _tasks = LocalFileProvider(cfg["tasks"]["path"])
    elif which == "todoist":
        from .todoist import TodoistProvider

        _tasks = TodoistProvider(cfg["tasks"]["token"])
    else:
        from .google_tasks import GoogleTasksProvider

        _tasks = GoogleTasksProvider(cfg["tasks"]["tasklist"])

    if cfg["mail"]["provider"] == "gmail":
        from .gmail import GmailProvider

        _mail = GmailProvider(cfg["mail"]["address"])
    else:
        _mail = None

    # Calendar is Google's alone. Todoist and a text file have none, so the
    # dashboard drops the column rather than pretending.
    if which == "google":
        from .google_tasks import GoogleCalendar

        _calendar = GoogleCalendar()
    else:
        _calendar = None
    _resolved = True


def tasks():
    _resolve()
    return _tasks


def mail():
    _resolve()
    return _mail


def calendar_or_none():
    _resolve()
    return _calendar
