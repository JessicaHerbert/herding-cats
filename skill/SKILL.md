---
name: rosie:herding-cats
description: Open the working day as a live scratch pad. Pulls today's and overdue Google Tasks, reads today's calendar, flags scheduling collisions, sweeps Slack for commitments Jess made or was asked for, and seeds a running todo list that stays visible for the rest of the session. Use when Jess says "herding cats", "/rosie:herding-cats", "set up my day", "what's on today", "scratch pad", "keep a todo list for me today", or opens a session intending to bounce between questions all day. Local only, never publishes anywhere. For the fuller external-meeting prep that publishes to Notion, use a fuller briefing skill instead.
---

# Herding Cats

The day opener. This skill does one job: put today on a single screen and keep a todo list alive underneath the rest of the session.

This is deliberately lighter than `rosie:morning-brief`. That skill does deep external-meeting prep and publishes a page to Notion. This one reads, flags, and holds a list. It never publishes anything.

## What it produces

Four short sections, in this order, then a todo list:

1. **Due today** - Google Tasks due today, with the calendar block each one is scheduled into if there is one.
2. **Overdue** - tasks past due that never got closed. These are the ones that quietly rot.
3. **Today's shape** - the calendar as a scannable table, meetings and focus blocks together.
4. **Collisions and commitments** - overlapping events, tasks scheduled on top of meetings, and anything from Slack that looks like a promise.

Then seed the session todo list from what surfaced.

## Step 1: Tasks

The list is your Google Tasks list. Get its ID with `gws tasks tasklists list` and put it in `app/state.py`.

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

## Step 4: Slack sweep

Look for commitments made or received since the last working day. Scope is deliberately tight: things Jess was pulled into, not everything happening at your company.

Search for:
- Messages that @-mention Jess.
- Threads Jess replied in.
- Her DMs.

Use `slack_search_public_and_private` with `include_context=false` and a tight limit, since broad queries blow the token cap. Always pass a date bound (`after:<yesterday>`), because an undated search is recency-windowed in a way that is not the same as "recent".

What counts as worth surfacing:
- Jess said she would do something ("I'll get you", "let me pull that", "I can have that by").
- Someone asked her for something and she has not answered.
- A decision landed that changes work she owns.

What does not:
- General channel chatter she was not part of.
- Anything where she was only tagged as an FYI.
- Threads about customers she is not directly working.

Per the task-suggestion rule, only surface items where Jess is directly mentioned or participating.

### Privacy boundary

DM content can be read here for Jess's own context. It stays in this session. Never carry a DM quote, summary, or attribution into a Notion page, a Slack message, a doc, or any artifact another person will read. This skill produces no artifact, which is what makes reading DMs acceptable in the first place.

## Step 5: Seed the todo list

Build the running todo list from what surfaced: tasks due today, unresolved collisions, and any Slack commitment Jess confirms is real. Keep it visible and update it through the session as she throws new items in.

The list is the point of the skill. Everything above is just how it gets populated.

## Step 6: Open the day file

Write `rosie/daily/YYYY-MM-DD.md` at the open, seeded from the sweep. One file per day.

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

- **Never publish.** No Notion page, no Slack message, nothing anyone else can see. The one file this skill writes is the local day file in `rosie/daily/`, which is a private working record. If Jess wants something written up for other people, that is a separate confirmed step through whichever skill owns that output.
- **Write the day file as you go.** Appending a decision the moment it lands takes one line. Reconstructing the day at 6pm is the thing that killed the last two attempts at this.
- **Never batch-create tasks.** New items surfaced from Slack are suggestions until Jess says to capture them. Hand off to `rosie:task` for the actual write.
- **Do not re-run the full sweep on every question.** Run it once at the open, then just maintain the list. Jess uses this as a scratch pad between meetings, so a five-tool-call refresh every time she asks something small defeats the purpose.
- **When a question that comes up mid-session is not a straight lookup, offer a dedicated session.** A subagent keeps her in this window and reports back only the conclusion; a new terminal window is better when she will iterate for a while. Ask which, do not just start digging.
- **Keep it short.** Bullets and tables. The whole open should fit on one screen.
