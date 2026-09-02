"""Bridge to the claude CLI.

The CLI is used rather than the Agent SDK because Claude Code already holds
authenticated connections to fifteen MCP servers. Re-establishing those inside
a separate process would mean re-authing every one of them.
"""

import asyncio
import json
from pathlib import Path

CWD = str(Path.home() / "tools-and-projects" / "rosie")

# One session id per app run, so the conversation keeps context across turns.
_session: str | None = None


def reset() -> None:
    global _session
    _session = None


async def ask(prompt: str):
    """Run a turn, yielding events as they arrive.

    Yields dicts: {"type": "tool"|"text"|"done"|"error", ...}
    """
    global _session

    args = [
        "claude", "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
    ]
    if _session:
        args += ["--resume", _session]

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=CWD,
    )

    assert proc.stdout is not None
    try:
        async for raw in proc.stdout:
            line = raw.decode().strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            for out in _translate(event):
                yield out

            if event.get("session_id"):
                _session = event["session_id"]
    finally:
        await proc.wait()

    if proc.returncode != 0:
        stderr = (await proc.stderr.read()).decode() if proc.stderr else ""
        yield {"type": "error", "message": stderr.strip()[:400] or "claude exited nonzero"}
    else:
        yield {"type": "done"}


def _translate(event: dict):
    """Turn CLI stream-json into the small event set the UI needs."""
    kind = event.get("type")

    if kind == "assistant":
        for block in event.get("message", {}).get("content", []):
            if block.get("type") == "text" and block.get("text"):
                yield {"type": "text", "text": block["text"]}
            elif block.get("type") == "tool_use":
                yield {"type": "tool", "name": block.get("name", "tool")}

    elif kind == "result":
        # The final result repeats the last assistant text, so only surface it
        # when it carries an error the stream did not already show.
        if event.get("is_error"):
            yield {"type": "error", "message": str(event.get("result", ""))[:400]}
