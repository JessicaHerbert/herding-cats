"""The catch-up sweep, run from the dashboard button.

This is the narrow half of the herding-cats skill. The full skill opens a day:
calendar, collisions, a seeded todo list, a fresh day file. None of that is
wanted from a button pressed at 3pm. What is wanted is the one thing no other
system records, which is what got finished since the last look.

The prompt points at the installed skill rather than restating its rules here.
The evidence rules are long and they change, and a copy of them in this file
would drift from the skill within a week of the first edit.
"""

import json
import shutil
import time
from pathlib import Path

from . import paths, state

# How long a sweep stays fresh. Each run is a full Claude Code turn across
# several MCP servers, so an unguarded button gets pressed far more often than
# the work justifies.
COOLDOWN = 900

# The model that does the judging. Pinned rather than inherited, so a
# scheduled job's cost does not depend on whatever model the CLI happens to
# default to.
#
# Measured on the first logged run: opus cost $1.35 of a $1.60 sweep, on 20
# input tokens and 5,795 output. The spend is the parent WRITING, not reading
# what the gatherers found, so the two levers are the model and the length of
# the reply. Both are pulled: sonnet here, and a hard cap on the summary in
# the prompt below.
MODEL = "sonnet"

# What the sweep is allowed to do without a prompt. A headless run stops dead
# on a permission dialog nobody is watching, and from the dashboard that is
# indistinguishable from a sweep that found nothing.
#
# Everything granted is a read except the dashboard POSTs, which are the whole
# point of the run and both show up in the Done panel with an undo. The blanket
# --dangerously-skip-permissions would have been one line instead of this list,
# and it would also let a background process run anything at all, so the list
# stays even though curl and sqlite3 within it are broader than one endpoint.
# Gathering is mechanical: run a query, report what came back. Judging whether
# something counts as finished work is not. Splitting them puts the bulk of the
# tokens on a cheap model and keeps the default one for the part that decides
# what lands in the pile, which matters at ten scheduled runs a weekday.
#
# Each gatherer reports raw findings and explicitly does NOT decide anything.
# A subagent that judges is the failure mode here: it has less context than the
# parent, cannot ask, and its conclusion arrives looking as confident as the
# parent's own.
def agents() -> dict:
    return {
        "sweep-messages": {
            "description": (
                "Gathers raw Slack and Gmail activity for a time window. "
                "Reports what was found verbatim and judges nothing."
            ),
            "model": "haiku",
            "tools": [
                "Bash",
                "mcp__plugin_slack_slack__slack_search_public_and_private",
                "mcp__plugin_slack_slack__slack_read_thread",
                "mcp__plugin_slack_slack__slack_read_channel",
            ],
            "prompt": (
                "You gather evidence. You never decide what it means.\n\n"
                "Report every item with its timestamp, its author, and where "
                "it came from. Quote the text rather than summarizing it, "
                "since the caller judges wording you would flatten.\n\n"
                "Rules that change the answer:\n"
                "- Gmail: use `in:sent`, never `from:me`. Superhuman keeps "
                "live drafts that carry her address and look sent.\n"
                "- Slack: `from:<@UALHUAYEQ>` for what she sent, "
                "`\"<@UALHUAYEQ>\"` for what mentions her. The `to:` modifier "
                "matches DMs only, never channel mentions.\n"
                "- Slack search returns newest-first at 20 per page, so one "
                "page is never the window. Follow the next_cursor in "
                "pagination_info until a page's oldest message is older than "
                "the window start or the cursor ends. Report the page count "
                "and the oldest timestamp you saw; a page-1 read is not "
                "evidence of a quiet window.\n"
                "- Read a whole thread before reporting it, and say who it is "
                "addressed to and who spoke last. Never describe a thread as "
                "an ask on her just because her name appears in it.\n"
                "- Report an empty result as empty. Never fill a gap.\n"
                "- Be terse. One line per item: timestamp, who, "
                "and the quoted text. No preamble, no narration "
                "between tool calls, no summary of your own "
                "process, no restating the brief. If there is "
                "nothing in the window, reply exactly: none. "
                "Your whole reply is read by another model that "
                "pays for every word of it."
            ),
        },
        "sweep-activity": {
            "description": (
                "Gathers file, doc and local activity for a time window from "
                "the docs API and the usage database. Judges nothing."
            ),
            "model": "haiku",
            "tools": ["Bash", "Read", "Grep", "Glob"],
            "prompt": (
                "You gather evidence. You never decide what it means.\n\n"
                "Report every item with its timestamp and its source.\n\n"
                "Rules that change the answer:\n"
                "- The activity database has ALREADY been copied somewhere "
                "you can read, and the caller gives you the path. Use that "
                "path. Do not look under ~/Library, which is sandboxed and "
                "will fail. If no path was given, skip that source and say "
                "so in one clause.\n"
                "- The dashboard's /api/docs endpoint (the caller gives you "
                "the base URL) lists every file and Notion page edited in "
                "ANY Claude session, named, newest first. Report every row "
                "in the window. This is the only view of work done in "
                "another window, so no row may be skipped.\n"
                "- Read the docs feed IN FULL: save it to a file and parse "
                "it with jq or python. A `head -c` slice or an inline "
                "preview drops entries from the middle and end with no "
                "visual sign. Report the total row count you parsed.\n"
                "- For a docs row whose session you cannot name, run "
                "`ccvault search \"<name or topic>\" after:<window start "
                "date>` and quote the transcript lines that say what that "
                "session was doing. ccvault reports raw lines; quote them "
                "rather than paraphrasing.\n"
                "- `app_sessions.start_time` is a REAL Unix epoch, not a "
                "datetime string. Comparing it to '2026-09-14 22:00:00' "
                "silently returns zero rows. Convert with "
                "`date -j -f \"%Y-%m-%d %H:%M:%S\" \"<ts>\" +%s` first.\n"
                "- Time spent in an app and keystroke counts are NOT "
                "completed work. Report them as activity and let the caller "
                "decide. Never call one a finished task.\n"
                "- A zero result is only real once the same query is proven "
                "able to return rows. Re-run without the time filter and "
                "report the total you saw.\n"
                "- Report an empty result as empty. Never fill a gap.\n"
                "- Be terse. One line per item: timestamp, who, "
                "and the quoted text. No preamble, no narration "
                "between tool calls, no summary of your own "
                "process, no restating the brief. If there is "
                "nothing in the window, reply exactly: none. "
                "Your whole reply is read by another model that "
                "pays for every word of it."
            ),
        },
    }


def allowed() -> list[str]:
    return [
        # The parent reaches the gatherers above through Task. Without it the
        # --agents definitions are inert and everything runs on the default
        # model, which is the expensive shape this split exists to avoid.
        "Task",
        # Broad on curl rather than one pattern per endpoint. The narrow forms
        # were tried first and every one of them missed: matching works on the
        # command prefix, and the agent picks its own flag order, adds -o, or
        # pipes the result, so a pattern built around one exact spelling
        # refuses the same request written slightly differently. Three
        # consecutive denials ended one test run before it swept anything.
        "Bash(curl:*)",
        "Bash(gws:*)",
        "Bash(ccvault search:*)",
        "Bash(gh search:*)",
        "Bash(gh pr list:*)",
        "Bash(sqlite3:*)",
        # start_time in the activity database is an epoch float, so reading
        # a window out of it means converting a date string first. The copy
        # itself is done by the app before the run, since Claude Code
        # sandboxes ~/Library whatever is granted here.
        "Bash(date:*)",
        "Read",
        "Grep",
        "Glob",
        # Deliberately NOT granted:
        #
        # "Skill" loaded the whole 455-line SKILL.md every run, about 6,400
        #   tokens, when the sweep needs two of its steps. Those rules are
        #   inlined in this prompt instead.
        # "TodoWrite" is a scratchpad for a human-facing session. Nobody
        #   reads it here and every write is output tokens.
        # "ScheduleWakeup" was reached for four times in one run, building
        #   a loop the parent then abandoned as "not the right mechanism".
        #   An unattended sweep must never schedule anything.
        "mcp__plugin_slack_slack__slack_search_public_and_private",
        "mcp__plugin_slack_slack__slack_read_thread",
        "mcp__plugin_slack_slack__slack_read_channel",
        "mcp__grain__list_meetings",
        "mcp__grain__search_in_transcripts",
    ]


PROMPT = """Find work Jess finished between {lo} and {hi} today and log it.
Nothing else. The window opened at {lo}, which is {since}, and closes at
{hi}. Both ends are real: anything stamped after {hi} has not happened yet
as far as this run is concerned, and anything before {lo} was covered by an
earlier sweep.

This used to load the rosie:herding-cats skill, which cost about 6,400 tokens
of its 455 lines every run to use two of its steps. The two steps are below.
Do not go looking for the skill file; everything needed is in this prompt.
The trade is that these rules now live here AND in the skill, so an edit to
one does not reach the other. Change both, or the sweep and the interactive
run start judging by different rules.

No calendar, no collisions, no todo list, no day file, no due-today or
overdue reporting. Do not write a todo list and do not schedule anything:
there is no one watching and nothing to wake up for.

Read the open task list first, though. A completion is matched against it,
and skipping that read is how a finished task gets logged twice.

Log ONLY the "completed, strong evidence" bucket, and log it without stopping
to ask. Strong means the artifact exists and is public: a Slack message posted,
mail carrying the SENT label, a Notion page published, a PR merged, a task
closed outside the dashboard. That is the skill's existing rule and the reason
behind it holds here: every cat is listed in the Done panel and each one has
an undo, so a wrong one costs a click rather than a correction.

This may be running unattended on the hourly schedule rather than from the
button, so nobody is necessarily watching. That raises the bar rather than
lowering it. Never ask a question, since there is no one to answer it and the
run will simply hang. Never infer a completion from activity alone: keystrokes
in an app, a file edited, or time spent somewhere is where to LOOK, never
something to log. When the evidence is ambiguous, put it under "weak:" and
move on rather than guessing, because an unattended wrong cat can sit in the
pile for hours before she sees it.

Date every artifact against the window before counting it. A draft, a file or
a thread that predates the window is not new work, and a raw count of drafts
or open threads says nothing about what happened this hour.

Weak-evidence items are not logged, but do NOT drop them silently. An unsent
draft or a doc edited and never shared is invisible everywhere else, so list
them at the end under "weak:" for her to look at.

Log through the dashboard API at {base} so each one earns its cat:

  curl -s -X POST {base}/api/done -H 'content-type: application/json' -d '<json>'
  curl -s -X POST {base}/api/task/<id>/complete -H 'content-type: application/json' -d '<json>'

Cover every source the skill lists, over the shorter window. Do not drop
/api/docs or the activity tracker, since those are the only view of work done
in another window. Notion rows in /api/docs arrive with their real names,
resolved and cached by the app, so a named Notion page edit is reportable
evidence and no longer a row of "(untitled in transcript)". When a docs row
comes from a session you have no other record of, ask ccvault what that
session was doing before you judge it; `ccvault search` is granted.

Delegate the GATHERING to the two subagents, in parallel in one message:
`sweep-messages` for Slack and Gmail, `sweep-activity` for /api/docs, the
usage database and any repo activity. Give each BOTH ends of the window,
{lo} and {hi}, not just the start. Give sweep-activity the
dashboard URL {base} for the docs call. They run on a cheaper model and
report raw findings.

The Slack filter must carry both bounds. `on:<day>` alone returns the day's
newest messages sorted newest-first, so with a `limit` the window's messages
fall off the end and the run sees only what happened after it. Use
`after:` and `before:` around the window instead, and treat any returned
message stamped outside {lo}-{hi} as proof the filter did not apply: say so
and re-run it bounded rather than reporting what came back. Slack's
`after:`/`before:` are EXCLUSIVE of the dates given, so today means
`after:<yesterday> before:<tomorrow>`, and pass `sort_dir=asc` so a
`limit` keeps the window rather than the newest messages.

{usage}

Do the JUDGING yourself, on everything they return. That is the whole point of
the split, so do not ask a subagent whether something counts as finished, and
do not take a subagent's word that something is done. They report artifacts;
you decide what cleared the bar. If a report is thin or a query looks like it
silently returned nothing, re-run that one yourself rather than accepting it.
A gatherer that reports Slack without a page count and an oldest timestamp, or
docs without a total row count, stopped short of the window: send it back
rather than judging from the partial read.

Then reply with one short line per item logged, then any weak items. No
preamble, no closing summary, no offer of next steps. If nothing cleared the
strong bar and there is nothing weak either, reply exactly: nothing new.

HARD LIMITS on that reply, because it is the single biggest cost in this run
and it is read in a tooltip:

- One line per item. A line is one sentence, under 25 words. Never a
  paragraph, never two sentences joined by a semicolon.
- At most 5 weak items. If more turn up, keep the 5 that most look like
  unfinished work and drop the rest silently.
- No reasoning about your own process, no narrating which tools you ran, no
  file paths to scratch files, no explanation of what you could not verify
  beyond four words ("could not verify publish").
- The whole reply stays under 150 words. Going over is a failure of the run,
  not a thorough answer.

Do not think out loud in the reply. Work it out, then write only the result.

Say NOTHING between tool calls. One measured run wrote nine separate blocks
of commentary before its answer, all of it narration: "Now dispatching the
two gathering subagents", "Waiting on the activity sweep", "Both sweeps are
back". Every one is output tokens for a line nobody reads, since only the
final block reaches the dashboard. Call the tools, then write the answer.

The reply begins with the first logged item or with "weak:" or with "nothing
new". It never begins with a heading, never with "Both sweeps are in", never
with a report of what each gatherer returned, and never with the word "Now".
Nobody reads this to learn how the sweep went, only what it found.

Ignore edits to this app's own repo. A sweep that reports the herding-cats
source as her finished work is reporting the sweep's own surroundings.
"""


def _state_file():
    return paths.home() / "sweep.json"


def last() -> dict:
    """When the last sweep ran and what it found."""
    path = _state_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


# Where the activity tracker keeps its data, and where the sweep reads it.
#
# The agent cannot read the original. Claude Code sandboxes paths under
# ~/Library regardless of what the tool allowlist grants, so every run spent
# tokens discovering it could not open the file and then reported the gap as
# a limitation. The app has no such restriction, so it stages a copy the
# agent can reach.
#
# Copying is required anyway: the tracking daemon holds the database open, so
# reading the live file risks a torn read.
USAGE_DB = Path.home() / "Library/Application Support/computer-usage/usage.db"
USAGE_COPY = Path("/tmp/herding-cats-usage.db")


def stage_usage_db() -> str:
    """Copy the activity database somewhere the agent can read it.

    Returns the path to use, or "" when the tracker is not installed or the
    copy fails. An empty string means the prompt tells the agent to skip that
    source outright rather than spend a tool call finding out.
    """
    if not USAGE_DB.exists():
        return ""
    try:
        shutil.copy2(USAGE_DB, USAGE_COPY)
        return str(USAGE_COPY)
    except OSError:
        # Not fatal. Every other source still works, and the sweep saying
        # nothing about local activity beats it failing outright.
        return ""


def trim_summary(text: str, max_words: int = 150) -> str:
    """Drop process narration and cap the length.

    The prompt asks for this and three runs in a row ignored it, opening with
    "Both sweeps are in. Now judging." and a triage walkthrough. A prompt is
    a request; this is the guarantee. It runs on the way into storage, so the
    tooltip and the runs panel never show the narration even when the model
    writes it anyway.
    """
    lines, kept = (text or "").splitlines(), []
    for line in lines:
        stripped = line.strip()
        low = stripped.lower().lstrip("*# ")
        # Openers seen in real runs. Each one is the sweep describing itself
        # rather than reporting what it found.
        if low.startswith((
            "both sweeps", "now judging", "applying triage", "messages sweep",
            "activity sweep", "let me", "i'll ", "i will ", "first,", "okay",
            "here is what", "here's what", "summary:", "judging:",
        )):
            continue
        kept.append(line)

    out = "\n".join(kept).strip() or (text or "").strip()
    words = out.split()
    if len(words) > max_words:
        out = " ".join(words[:max_words]).rstrip(",.;:") + " ..."
    return out


def record(logged: int, summary: str) -> None:
    _state_file().write_text(json.dumps({
        "at": time.time(),
        "clock": state.today().strftime("%H:%M"),
        "day": state.working_day(),
        "logged": logged,
        # The caller passes only the final text block, so this is the answer
        # rather than the narration and the head is the part worth keeping.
        "summary": trim_summary(summary)[:4000],
    }))


def cooling() -> int:
    """Seconds left on the cooldown, or 0 when a sweep is allowed."""
    at = last().get("at")
    if not at:
        return 0
    return max(0, int(COOLDOWN - (time.time() - at)))


def window() -> tuple[str, str]:
    """The window to sweep, as an explicit (start, end) pair of HH:MM clocks.

    Both ends matter. `since()` used to hand over a start alone, and the
    gatherer then chose its own end: the 21:06 run was told "since 19:06" and
    came back with messages timestamped 21:51 and 22:06, which had not
    happened when the window opened. Its own summary called them "stale
    results outside the window" and logged nothing from the real gap.

    The end is the current clock rather than open-ended, so the search filter
    built from this pair can bound both sides.
    """
    prev = last()
    now = state.today().strftime("%H:%M")
    if prev.get("day") == state.working_day() and prev.get("clock"):
        return prev["clock"], now
    return "00:00", now


def since() -> str:
    """The window as prose, naming the last sweep when there was one.

    Kept because the prompt reads better naming the previous run than quoting
    a bare clock, and because the day-boundary rule lives here: the first
    sweep of a working day covers the day from its start rather than the last
    24 hours, so a run at 9am does not re-report yesterday evening.
    """
    prev = last()
    if prev.get("day") == state.working_day() and prev.get("clock"):
        return f"{prev['day']} {prev['clock']} (the last sweep)"
    return f"the start of the working day, {state.working_day()}"


def prompt(port: int) -> str:
    """Build the run's prompt, staging anything the agent cannot reach itself.

    The activity database is copied here rather than by the agent, because
    Claude Code sandboxes ~/Library whatever the tool allowlist says. Runs
    were spending a tool call discovering that and reporting it as a finding.
    """
    lo, hi = window()
    staged = stage_usage_db()
    usage = (
        f"The activity database is already copied to `{staged}` - pass that "
        "exact path to `sweep-activity`, which cannot reach the original."
        if staged else
        "The activity tracker is unavailable this run, so tell "
        "`sweep-activity` to skip it rather than hunt for the file."
    )
    return PROMPT.format(since=since(), lo=lo, hi=hi,
                         base=f"http://127.0.0.1:{port}", usage=usage)
