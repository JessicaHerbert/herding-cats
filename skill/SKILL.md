---
name: rosie:herding-cats
description: Open the working day, or catch up on what has happened since the last look. Sweeps every system Jess works in - Google Tasks, calendar, Slack (what she sent, what mentions her, DMs), Gmail (sent, and threads awaiting her reply), Notion and local file edits across every Claude session, a local activity tracker for work that left no artifact, and Grain calls - then judges each signal: did she finish something, is someone still waiting, or is it already handled. Logs completions to the herding-cats dashboard so they earn a cat, and surfaces new todos for her to confirm. Use when Jess says "herding cats", "/rosie:herding-cats", "set up my day", "what's on today", "what did I get done", "what did I complete", "catch me up", "scratch pad", or opens a session intending to bounce between questions all day. Local only, never publishes anywhere. For the fuller external-meeting prep that publishes to Notion, use a fuller briefing skill instead.
---

# Herding Cats

The day opener. This skill does one job: put today on a single screen and keep a todo list alive underneath the rest of the session.

This is deliberately lighter than `rosie:morning-brief`. That skill does deep external-meeting prep and publishes a page to Notion. This one reads, flags, and holds a list. It never publishes anything.

## Two modes

**Open** is the first run of the day. Full sweep, seed the day file, build the
list.

**Catch-up** is every run after that. Do not re-run the whole sweep; look only
at what changed since the last one, and lead with what moved rather than
restating the day. The gap since the previous run is the window to search.

## What it produces

Four short sections, in this order, then a todo list:

1. **Done since the last look** - what the sweep found evidence of, logged and
   cat-earning. This section leads on a catch-up run, because it is the part
   nothing else in her stack records.
2. **Due today** - Google Tasks due today, plus anything starred for today, with
   the calendar block each one is scheduled into if there is one.
3. **Overdue** - tasks past due that never got closed. These are the ones that
   quietly rot.
4. **Today's shape** - the calendar as a scannable table.
5. **Collisions and what is waiting** - overlapping events, tasks with no block,
   and the asks that survived the already-handled check.

Then seed the session todo list from what surfaced.

## Step 1: Tasks

The list is whichever task list the app is configured against. The setup wizard (`python -m app.setup`) writes that choice to `~/.herding-cats/config.toml`, and for Google Tasks it lists your task lists so you can pick one.

```
gws tasks tasks list \
  --params '{"tasklist":"<YOUR_TASKLIST_ID>","showCompleted":false,"maxResults":100}' \
  --format json
```

Split the results into three buckets by the `due` field: due today, overdue (due date before today), and no due date. Report the first two. Do not dump the undated backlog, since it is long and it is not what today is about.

Google Tasks stores `due` as a UTC midnight timestamp, so compare on the date portion only. A task due `2026-09-01T00:00:00.000Z` is due September 1 regardless of Jess's timezone.

## Step 2: Calendar

Set your timezone here. Build the day window from local midnight to local midnight.

```
gws calendar events list \
  --params '{"calendarId":"primary","timeMin":"<today>T00:00:00-04:00","timeMax":"<tomorrow>T00:00:00-04:00","singleEvents":true,"orderBy":"startTime"}' \
  --format json
```

Pipe through `2>/dev/null` because `gws` writes diagnostics to stderr and they corrupt a JSON parse.

Present start, end, and title. Note the `eventType` field, since it tells you what a block actually is:

- `focusTime` blocks that carry a `tasks.google.com` link in the description are Google Tasks Jess dragged onto her calendar. Match these back to the task list by title so a task and its block report as one line, not two.
- `workingLocation` events are where she is sitting, not commitments. Mention only if it changed.
- `default` events are real meetings.

## Step 3: Collisions

This is the part that earns the skill. Check for three kinds:

- **Two meetings overlapping.** Compare every pair of `default` events for intersecting time ranges.
- **A task block sitting under a meeting.** A `focusTime` block that overlaps a `default` event means the task will not happen.
- **A task due today with no block at all.** It is due and nothing is protecting time for it.

Report each collision as a plain sentence naming both sides and the time. Do not editorialize about which one should win, since that is Jess's call.

## Step 4: The evidence sweep

The point of this step is not to list what happened. It is to answer two
questions about every signal found: **did Jess finish something**, and **is
someone waiting on her**.

Real work is rarely task-shaped. On 2026-09-02 five completed items were
invisible to the dashboard because they were a Slack announcement, three Notion
pages, and a handoff, none of which started life as a Google Task. Sweeping only
Tasks and mentions misses most of a real day.

Run these in parallel. Each one is a source of evidence, not a report.

### What Jess sent

- `from:<@YOUR_SLACK_ID> after:<since>` across all channel types. This is the
  single highest-value query and the old version of this skill did not run it.
  A message she posted is usually a thing she did.
- Sent mail: `gws gmail users messages list --params '{"userId":"me","q":"in:sent after:YYYY/MM/DD"}'`.
  **Use `in:sent`, never `from:me`.** A mail client that keeps a live draft in
  Gmail while you compose (Superhuman does this) leaves drafts that carry your
  address as sender, so `from:me` returns them looking exactly like sent
  messages. `in:sent` excludes drafts at the query and saves a per-message `get`
  on every hit. If a `from:me` search is ever used anyway, check `labelIds` on
  every result and count only `SENT`, because a `DRAFT` label there means the
  message never left.

### What is aimed at her

- `"<@YOUR_SLACK_ID>" after:<since>` in public and private channels. The `to:`
  modifier matches DMs only, never channel mentions.
- DMs: `to:me after:<since>` with `channel_types=im,mpim`.
- Mail awaiting a reply: someone else spoke last AND she is on the To line, not
  Cc. Cc means the reply belongs to whoever was addressed. Unread is the wrong
  filter, since anything that actually needs an answer has usually been read.

### What she touched

- `GET /api/docs?days=1` on the dashboard covers Notion pages and local files
  she edited, with an edit count and timestamp. It reads the session
  transcripts under `~/.claude/projects`, so it already spans EVERY Claude
  session rather than the one you are in, and it catches files written through
  Bash as well as through Edit and Write. Work done in another window shows up
  here and nowhere else in this sweep.
- `ccvault search "<term>" after:<date>` for what she worked on in other Claude
  sessions. Useful when work landed in a repo or a doc rather than a message.
- Recent commits or PRs if a repo is in play: `gh search prs --author=@me`.
- A local activity tracker, if one is running, is the only source that sees
  work leaving no artifact at all. This setup uses one that writes SQLite to
  `~/Library/Application Support/computer-usage/usage.db`; query `app_sessions`
  for `app_name`, `window_title`, `browser_url`, and `keystroke_count` in the
  window. Do not invoke its binary to query it, since that is the tracking
  daemon and it will hang.

  What it is FOR is the gap between effort and artifact. Heavy keystrokes in a
  Slack channel with no message posted in that channel means something was
  typed and abandoned in the composer, which is the same failure as an unsent
  mail draft and just as invisible. One run caught 282 keystrokes across six
  minutes in a channel that never produced a single message. Cross-check any
  app with real input against what that app actually published before deciding
  nothing happened.

  Time-per-app is NOT evidence of a completed thing, so never log a cat from it
  alone. It tells you where to go looking and what to ask about.

### Grain

Check Grain for calls that happened since the last sweep, since a call is often
where a commitment gets made. `list_meetings` returns a summary inline, which is
usually enough; `search_in_transcripts` when looking for a specific topic. Fathom
covers a different set of calls, so a clean miss in one is not absence.

## Step 4b: Judge the evidence

For every signal, decide which bucket it lands in. This is the part that makes
the skill worth running.

**Completed, strong evidence.** Log it without asking. Strong means the artifact
exists and is public: a Slack message posted, an email with the `SENT` label, a
Notion page published, a PR merged, a task closed in Google Tasks. Log through
the dashboard so it earns its cat: `POST /api/done {"text": "..."}` for work that
was never a task, or `POST /api/task/<id>/complete` for one that was.

**Completed, weak evidence.** Ask before logging. Weak means the signal is
consistent with the work being done but does not prove it: an unsent draft, a
thread she replied in without resolving, a doc edited but not shared, a branch
pushed with no PR. A draft reply to a partner inquiry was once logged as a sent
reply on exactly this mistake. Drafts are the common case rather than the
exception, since an abandoned one can sit for days looking like finished work.

**Already handled.** Read the thread before surfacing an ask. On 2026-09-02, five
of nine apparent asks were already answered by the time the sweep ran, and
reporting them as open made the list noise instead of signal.

**Genuinely waiting on her.** Surface it. If it should become a task, say so and
wait for a yes; never batch-create.

**Neither.** Drop it. Channel chatter, FYI tags, and threads about customers she
is not working do not belong in the output.

### Matching against the list

Once the completed set is known, check each one against the open tasks. Three
outcomes: it matches an open task (complete that task, which earns the cat), it
matches nothing (log via `/api/done`), or it partially matches (ask, because
closing a task whose other half is unfinished is worse than leaving it open).

## Step 5: Seed the todo list

Build the running todo list from what surfaced: tasks due today, unresolved collisions, and any Slack commitment Jess confirms is real. Keep it visible and update it through the session as she throws new items in.

The list is the point of the skill. Everything above is just how it gets populated.

## Step 6: Open the day file

Write `~/.herding-cats/daily/YYYY-MM-DD.md` at the open, seeded from the sweep. One file per day. That location follows `HERD_HOME` if it is set.

The file exists so Jess does not have to remember. Two previous attempts at this (`.eod-wraps/`, and a single file in `daily/`) both died because they were written at the end of the day, which is when there is the least appetite for writing anything. This one gets created at the open and appended to as the day goes, so there is nothing left to do at close-out.

Seed it with this shape:

```markdown
# YYYY-MM-DD, Dayname

## On the list
- [ ] <task due today> (<block time if scheduled>)
- [ ] <collision to resolve>

## Decisions
<!-- appended live -->

## Open threads
<!-- appended live -->

## Notes
<!-- appended live -->
```

### Appending during the day

Add to the file as things actually happen, not in a batch at the end. Three kinds of entry:

- **Decisions** get the choice and the reasoning, including what was ruled out. "Named the skill herding-cats, rejected flight-deck and coffee" is worth more later than just the outcome, because the reasoning is what stops the same question being reopened next month.
- **Open threads** get enough detail to resume cold: the IDs, the file paths, the query that worked, what the next step was. This is the scratchpad pattern, so write for a session that has none of today's context.
- **Notes** get answers to questions that came up, so a lookup done once does not get done again.

Keep entries short. A line or two each, timestamped only when the timing matters.

### What does not go in

- No DM quotes, names attached to opinions, or anything HR-adjacent. The file is local, but local files get read aloud and pasted into other places.
- No patient identifiers, chart content, or raw log rows.
- No customer names in anything that reads like a general how-to.

### At close-out

Update the checkboxes to reflect what actually got done, and note anything carrying to tomorrow. Do not rewrite the file into a narrative, since that is the end-of-day step that killed the last two attempts.

## Step 7: Close out (end of session)

When Jess signals she is done for the day, or asks to close out, walk the tasks that were due today and ask which got finished. Complete only the ones she confirms:

```
gws tasks tasks patch \
  --params '{"tasklist":"<YOUR_TASKLIST_ID>","task":"<taskId>"}' \
  --json '{"status":"completed"}' --format json
```

Never mark a task complete on inference. Working on something in this session is not the same as having finished it.

For anything that did not get done, offer to reschedule rather than leaving it to go overdue.

## Rules

- **Never publish.** No Notion page, no Slack message, nothing anyone else can see. The one file this skill writes is the local day file under `~/.herding-cats/daily/`, which is a private working record. If Jess wants something written up for other people, that is a separate confirmed step through whichever skill owns that output.
- **Write the day file as you go.** Appending a decision the moment it lands takes one line. Reconstructing the day at 6pm is the thing that killed the last two attempts at this.
- **Never batch-create tasks.** Discovered todos are suggestions until Jess says
  to capture them. Completions are the opposite: log strong evidence without
  asking, because the friction of confirming twenty items is what stops the
  record being kept at all.
- **Log through the dashboard, not the day file alone.** `POST /api/done` earns
  the cat and writes the day file in one call. Writing the file by hand skips
  the pile, which is the part she looks at.
- **Verify before believing a signal.** A `from:me` mail search returns unsent
  drafts alongside real sends, so query `in:sent` instead. A task can be
  completed on a phone. An ask in a thread may already be answered three
  replies down. Read the artifact, not the notification.
- **A delta sweep still covers every source, just over a shorter window.**
  Dropping sources rather than narrowing the window is what makes a re-run miss
  things, and the two most often dropped are the ones that need it least:
  `/api/docs` and the activity tracker are single calls and they are the only
  view of work done in another window or another session. A re-run that checks
  mail, Slack, and tasks alone will report a quiet hour that was not quiet.
  This has already happened.
- **Do not re-run the full sweep on every question.** Full sweep at the open,
  delta sweep on an explicit re-run, nothing on a passing question. Jess uses
  this as a scratch pad between meetings, so a ten-tool-call refresh every time
  she asks something small defeats the purpose.
- **Ask what she did.** The sweep finds artifacts, not intentions. Work that left
  no trace (a call she took, a decision she made, something she fixed by hand) is
  invisible to every query here, and asking once at the end of a catch-up run
  costs one line and catches what the tools cannot.
- **When a question that comes up mid-session is not a straight lookup, offer a dedicated session.** A subagent keeps her in this window and reports back only the conclusion; a new terminal window is better when she will iterate for a while. Ask which, do not just start digging.
- **Keep it short.** Bullets and tables. The whole open should fit on one screen.
