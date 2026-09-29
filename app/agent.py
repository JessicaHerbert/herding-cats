"""Bridge to the claude CLI.

The CLI is used rather than the Agent SDK because Claude Code already holds
authenticated connections to fifteen MCP servers. Re-establishing those inside
a separate process would mean re-authing every one of them.
"""

import asyncio
import json
import os
from pathlib import Path

# Where the CLI runs, which decides which project's skills and settings it
# picks up. A hardcoded personal path was wrong for anyone else's checkout, so
# this falls back to the repo itself.
CWD = os.environ.get("HERD_AGENT_CWD") or str(Path(__file__).parent.parent)

# One session id per app run, so the conversation keeps context across turns.
_session: str | None = None


def reset() -> None:
    global _session
    _session = None


async def ask(prompt: str, allow: list[str] | None = None,
              agents: dict | None = None, model: str | None = None):
    """Run a turn, yielding events as they arrive.

    Yields dicts: {"type": "tool"|"text"|"done"|"error", ...}

    `allow` is passed to --allowedTools. Without it a headless run stops on a
    permission prompt that nobody is watching for, which looks from the UI like
    the run simply did nothing. Grant the specific tools a job needs rather
    than reaching for --dangerously-skip-permissions, which would hand a
    background process the ability to run anything at all.

    `model` is passed to --model. Left unset the CLI uses whatever the user's
    default is, which for a scheduled job means the spend depends on a setting
    that has nothing to do with this app.

    `agents` is passed to --agents as a JSON object of subagent definitions.
    Each takes `description`, `prompt`, and optionally `model` and `tools`,
    so gathering can be pushed onto a cheaper model while the parent turn
    keeps the default one for judging. The caller must also grant "Task" in
    `allow`, or the parent has no way to reach them.
    """
    global _session

    args = [
        "claude", "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
    ]
    if model:
        args += ["--model", model]
    if agents:
        args += ["--agents", json.dumps(agents)]
    if allow:
        args += ["--allowedTools", *allow]
    if _session:
        args += ["--resume", _session]

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=CWD,
    )

    # Drain stderr concurrently rather than reading it at the end. It is a pipe
    # with a fixed OS buffer, and a chatty run that fills it blocks the child
    # forever while this side is still waiting on stdout.
    errors: list[bytes] = []

    async def drain():
        assert proc.stderr is not None
        async for chunk in proc.stderr:
            errors.append(chunk)

    draining = asyncio.create_task(drain())

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
        # A caller that stops consuming (the browser closed the stream) leaves
        # the CLI running otherwise, holding its MCP connections open.
        if proc.returncode is None:
            proc.terminate()
        await proc.wait()
        await draining

    if proc.returncode != 0:
        stderr = b"".join(errors).decode(errors="replace").strip()
        yield {"type": "error", "message": stderr[:400] or "claude exited nonzero"}
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

        # Cost and the per-model split arrive only on this event and are
        # nowhere in the session transcript, so a run not captured here
        # cannot be priced afterwards. `modelUsage` is keyed by full model
        # id, which is what shows whether the gatherers actually landed on
        # haiku or quietly inherited the parent's model.
        if "total_cost_usd" in event or "modelUsage" in event:
            yield {
                "type": "usage",
                "cost_usd": event.get("total_cost_usd"),
                "duration_ms": event.get("duration_ms")
                or event.get("duration_api_ms"),
                "num_turns": event.get("num_turns"),
                "models": {
                    model: {
                        "cost_usd": u.get("costUSD"),
                        "input": u.get("inputTokens"),
                        "output": u.get("outputTokens"),
                        "cache_read": u.get("cacheReadInputTokens"),
                        "cache_write": u.get("cacheCreationInputTokens"),
                    }
                    for model, u in (event.get("modelUsage") or {}).items()
                },
            }
