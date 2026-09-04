"""Documents touched across every Claude Code session.

Reads the session transcripts in ~/.claude/projects rather than watching the
filesystem, so it captures what was worked on deliberately and in which
project, and it survives a file being moved afterwards.
"""

import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from . import state

PROJECTS = Path.home() / ".claude" / "projects"
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
NOTION_TOOLS = {"mcp__notion__notion-update-page", "mcp__notion__notion-create-pages"}

# Under auto mode most files are written through Bash rather than Edit/Write,
# so a transcript can show a full day of work and no write-tool calls at all.
# These patterns pick the target back out of the command text. Each one must
# capture the path in group 1.
BASH_WRITE = (
    re.compile(r""">>?\s*['"]?(/[^\s'"|;&>]+)"""),           # cmd > /path, >> /path
    re.compile(r"""\b(?:tee)\s+(?:-a\s+)?['"]?(/[^\s'"|;&]+)"""),
    # sed -i: the LAST absolute path on the line is the target, since the
    # substitution expression itself is full of slashes and matches first.
    re.compile(r"""\bsed\s+(?=[^|;&]*-i\b)[^|;&]*\s['"]?(/[^\s'"|;&]+)\s*(?:$|[|;&])"""),
    re.compile(r"""\b(?:cp|mv)\s+[^|;&]*?\s['"]?(/[^\s'"|;&]+)\s*(?:$|[|;&])"""),
    # A heredoc'd python/script writes through open(...,'w'); the path is in
    # the body rather than the command, so match the open call directly.
    re.compile(r"""open\(\s*['"](/[^'"]+)['"]\s*,\s*['"][wa]"""),
)

# Noise: transient files and machinery that are not "documents" in any sense
# Jess would recognize.
SKIP_PARTS = (
    "/.claude/projects/", "/node_modules/", "/.venv/", "/site-packages/",
    "/tool-results/", "/.remember/", "/__pycache__/", "/.git/",
    "/herding-cats-app/",  # the app's own files are code, not documents
)
SKIP_PREFIX = ("/tmp/", "/private/tmp/", "/var/folders/")


# Documents are things with prose or data in them, not source code. A .py file
# is work, but it is not a document Jess would go looking for later.
CONTENT_EXT = {".md", ".markdown", ".csv", ".tsv", ".html", ".htm", ".pdf",
               ".txt", ".docx", ".xlsx", ".json"}

# JSON is mostly config and lockfiles; keep it only when the name suggests data.
JSON_KEEP = ("export", "data", "report", "snapshot", "results", "dump", "audit")

# Files that are machinery even though the extension qualifies.
SKIP_NAMES = {"package.json", "package-lock.json", "tsconfig.json", "uv.lock",
              "settings.json", "settings.local.json", "manifest.json",
              "readme.md", "claude.md", "agents.md"}


def _interesting(path: str) -> bool:
    if not path or not path.startswith("/"):
        return False
    if any(path.startswith(p) for p in SKIP_PREFIX):
        return False
    if any(part in path for part in SKIP_PARTS):
        return False

    name = os.path.basename(path).lower()
    if name in SKIP_NAMES:
        return False

    ext = os.path.splitext(name)[1]
    if ext not in CONTENT_EXT:
        return False
    if ext == ".json" and not any(k in name for k in JSON_KEEP):
        return False
    return True


def _bash_targets(command: str) -> list[str]:
    """Absolute paths a Bash command appears to write to.

    Deliberately conservative and absolute-only: a relative path cannot be
    resolved without knowing the shell's cwd at the time, and guessing wrong
    invents a document that was never touched. `_interesting` still filters
    whatever comes back, so a read-only match on a `.md` path is the worst
    case and it shows up as one spurious edit rather than a wrong file.
    """
    if not command:
        return []
    # A command that only exercises the parser (a test harness importing this
    # module) would otherwise register its fixture paths as real documents.
    if "_bash_targets" in command:
        return []
    hits: list[str] = []
    for pattern in BASH_WRITE:
        for match in pattern.finditer(command):
            path = match.group(1)
            if path not in hits:
                hits.append(path)
    return hits


def _project_label(session_file: Path) -> str:
    """Turn the encoded directory name back into something readable."""
    raw = session_file.parent.name.lstrip("-").replace("-", "/")
    home = str(Path.home()).lstrip("/").replace("/", "/")
    if raw.startswith(home):
        raw = raw[len(home):].lstrip("/")
    return raw.split("/")[-1] or raw or "unknown"


def touched(days: int = 7, limit: int = 40) -> dict:
    """Files and Notion pages written or edited in the window, newest first."""
    if not PROJECTS.exists():
        return {"docs": [], "days": days, "sessions": 0}

    cutoff = (datetime.now(state.TZ) - timedelta(days=days)).timestamp()
    found: dict[str, dict] = {}
    notion: dict[str, dict] = {}
    scanned = 0

    for session in PROJECTS.glob("*/*.jsonl"):
        try:
            if session.stat().st_mtime < cutoff:
                continue
        except OSError:
            continue
        scanned += 1
        project = _project_label(session)

        try:
            handle = session.open(errors="ignore")
        except OSError:
            continue

        with handle:
            for line in handle:
                if '"tool_use"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue

                when = rec.get("timestamp", "")
                for block in (rec.get("message", {}).get("content") or []):
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    name = block.get("name", "")
                    args = block.get("input") or {}

                    if name in WRITE_TOOLS or name == "Bash":
                        if name == "Bash":
                            paths = _bash_targets(args.get("command", ""))
                        else:
                            paths = [args.get("file_path", "")]
                        for path in paths:
                            if not _interesting(path):
                                continue
                            entry = found.setdefault(path, {
                                "path": path,
                                "name": os.path.basename(path),
                                "project": project,
                                "edits": 0,
                                "last": "",
                                "kind": "file",
                            })
                            entry["edits"] += 1
                            if when > entry["last"]:
                                entry["last"] = when
                                entry["project"] = project

                    elif name in NOTION_TOOLS:
                        page, title = _notion_ref(args)
                        if not page:
                            continue
                        # Normalise so the same page edited from two projects
                        # is one document, not two.
                        key = page.replace("-", "").lower()
                        entry = notion.setdefault(key, {
                            "path": page, "name": title, "project": project,
                            "edits": 0, "last": "", "kind": "notion",
                        })
                        entry["edits"] += 1
                        if when > entry["last"]:
                            entry["last"] = when
                            if title != "Notion page":
                                entry["name"] = title

    # Notion pages are documents too, so they belong in the same list rather
    # than as a footnote count.
    for page in notion.values():
        page["url"] = f"https://notion.so/{page['path'].replace('-', '')}"
        if page["name"] == "Notion page":
            # Titles are not recoverable from an update call, and fetching each
            # one live would mean an API round trip per refresh. The link is
            # what makes the row useful, so lean on that.
            page["name"] = "Notion page (untitled in transcript)"

    docs = sorted([*found.values(), *notion.values()],
                  key=lambda d: d["last"], reverse=True)
    for d in docs:
        d["when"] = _relative(d["last"])
        if d["kind"] == "file":
            d["dir"] = os.path.dirname(d["path"]).replace(str(Path.home()), "~")
            d["url"] = ""

    return {
        "docs": docs[:limit],
        "total": len(docs),
        "days": days,
        "sessions": scanned,
    }


def _notion_ref(args: dict) -> tuple[str, str]:
    """Pull a page id and a title out of a Notion tool call.

    Three shapes occur: page_id at the top level, page_id inside a JSON-encoded
    `data` string, and creation calls where the title is in pages[].properties.
    """
    title = "Notion page"

    pages = args.get("pages")
    if isinstance(pages, list) and pages:
        props = (pages[0] or {}).get("properties") or {}
        if props.get("title"):
            title = str(props["title"])[:70]
        # A creation call has no page id yet, so key on the parent. The title
        # must not become the id, or the resulting URL points at nothing.
        parent = (args.get("parent") or {}).get("page_id", "")
        return parent, title

    page_id = args.get("page_id")
    if not page_id:
        raw = args.get("data")
        if isinstance(raw, str):
            try:
                page_id = json.loads(raw).get("page_id")
            except json.JSONDecodeError:
                page_id = None
        elif isinstance(raw, dict):
            page_id = raw.get("page_id")

    return (str(page_id) if page_id else ""), title


def _relative(iso: str) -> str:
    if not iso:
        return ""
    try:
        when = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(state.TZ)
    except ValueError:
        return ""
    now = datetime.now(state.TZ)
    delta = now - when
    if delta < timedelta(minutes=2):
        return "just now"
    if delta < timedelta(hours=1):
        return f"{int(delta.total_seconds() // 60)}m ago"

    # Compare on the working day, not the calendar date. Work done at 23:50
    # belongs to the same day as work done the next morning at 09:00, and
    # calling it "yesterday" at breakfast is wrong.
    if _working_day_of(when) == state.working_day():
        return when.strftime("%H:%M")
    if delta < timedelta(days=2):
        return "yesterday"
    return when.strftime("%b %-d")


def _working_day_of(when: datetime) -> str:
    if when.hour < state.DAY_STARTS_AT:
        when -= timedelta(days=1)
    return when.strftime("%Y-%m-%d")
