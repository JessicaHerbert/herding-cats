---
name: rosie:herding-cats
description: Open the working day, or catch up on what has happened since the last look. Sweeps every system Jess works in - Google Tasks, calendar, Slack (what she sent, what mentions her, DMs), Gmail (sent, and threads awaiting her reply), Notion and local file edits across every Claude session, computer-usage for work that left no artifact, and Grain calls - then judges each signal: did she finish something, is someone still waiting, or is it already handled. Logs completions to the herding-cats dashboard so they earn a cat, and surfaces new todos for her to confirm. Use when Jess says "herding cats", "/rosie:herding-cats", "set up my day", "what's on today", "what did I get done", "what did I complete", "catch me up", "scratch pad", or opens a session intending to bounce between questions all day. Local only, never publishes anywhere. For the fuller external-meeting prep that publishes to Notion, use rosie:morning-brief instead.
---

# Herding Cats

The day opener. Jess runs seven functional areas and thinks about ten of them at once, so this skill does one job: put today on a single screen and keep a todo list alive underneath the rest of the session.

This is deliberately lighter than `rosie:morning-brief`. That skill does deep external-meeting prep and publishes a page to Notion. This one reads, flags, and holds a list. It never publishes anything.

## Two modes

**Open** is the first run of the day. Full sweep, seed the day file, build the
list.

**Catch-up** is every run after that. Do not re-run the whole sweep; look only
at what changed since the last one, and lead with what moved rather than
restating the day. The gap since the previous run is the window to search.

**The dashboard runs on port 8787.** Every `/api/*` call in this file means
`http://localhost:8787`. Port 9990 further down is a different app.

**There is a catch-up button, and it runs this skill.** `POST /api/sweep` runs
the evidence sweep below headless through the `claude` CLI and logs whatever
clears the strong-evidence bar. Two things follow from that.

**The scheduled sweep does NOT read this file.** Loading it cost about 6,400
tokens a run to use two of its steps, so steps 4 and 4b are copied into the
prompt in `app/sweep.py` instead. Editing the evidence rules here does not
change what the hourly job does. Change both, or the two start judging by
different rules.

It holds a lock and a 15-minute cooldown, so a manual run started while the
button is going will double-log the same evidence. Check `GET /api/sweep` for
`cooling` before starting a by-hand sweep. A POST during an active run returns
409; during the cooldown it returns 429 unless passed `?force=true`.

When Jess asks for a catch-up and the dashboard is already up, prefer the
button over doing it by hand. Doing it manually is for an open, for a window
the button cannot express, or when the button has already run and something
needs checking on top of it.

**Finding when the last run was.** Nothing records it, so it has to be derived,
and the obvious sources are both wrong. A bare `HH:MM` inside the day file's
Notes or Decisions is prose rather than a marker, and one such line was read as
a run time on 2026-09-04, setting the window ten hours too wide. The day file
also lags, because a completion logged through the dashboard UI does not append
to it, so its newest line can sit hours behind the real herd.

There are two records and they answer different questions, so read the one that
matches what you are doing.

`GET /api/sweep` is the record of the last full sweep, and it is the right
window for a catch-up run. It returns `day`, `clock`, `logged`, `summary` and
`cooling`. The summary carries what the previous run found and what it flagged
as weak, which is worth reading before re-reporting the same thing.

`GET /api/history` is the right source when a cat has been logged since that
sweep, because completions logged through the dashboard or written into the day
file do not update the sweep record. It returns `days`, newest first, each with
a `day` and a list of `cats`. The newest completion is the last `at` on
`days[0].cats`.

Do NOT reach for `GET /api/state` here. Its `herd` key is a summary carrying
only `today`, `total` and `days_kept`, with no cat records and no `at` at all,
so there is nothing there to read a time from.

Two traps in the `at` value itself. It is a bare `"HH:MM"` clock string with no
date, so it is meaningless without the `day` it sits under; always pair them.
And an `at` of `""` is normal for a cat synced out of the day file without a
timestamp, so skip the blanks rather than treating one as midnight.

Say which value was used and what window it produced, so a wrong one is visible
rather than silent.

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

The list is **Jess To Do**, ID `MTcyMDI1NTI0MzQxNTIyMzI4ODM6MDow`. If that ID stops working, re-fetch with `gws tasks tasklists list`.

```
gws tasks tasks list \
  --params '{"tasklist":"MTcyMDI1NTI0MzQxNTIyMzI4ODM6MDow","showCompleted":false,"maxResults":100}' \
  --format json
```

Split the results into three buckets by the `due` field: due today, overdue (due date before today), and no due date. Report the first two. Do not dump the undated backlog, since it is long and it is not what today is about.

Google Tasks stores `due` as a UTC midnight timestamp, so compare on the date portion only. A task due `2026-09-01T00:00:00.000Z` is due September 1 regardless of Jess's timezone.

## Step 2: Calendar

Jess is in `America/Indiana/Indianapolis`. Build the day window from local midnight to local midnight.

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

Work at Canvas is rarely task-shaped. On 2026-09-02 five completed items were
invisible to the dashboard because they were a Slack announcement, three Notion
pages, and a handoff, none of which started life as a Google Task. Sweeping only
Tasks and mentions misses most of a real day.

Run these in parallel. Each one is a source of evidence, not a report.

### What Jess sent

- `from:<@UALHUAYEQ> after:<since> before:<now>` across all channel types. This is the
  single highest-value query and the old version of this skill did not run it.
  A message she posted is usually a thing she did.
- **Paginate until the window start is reached.** The search returns 20 results
  per page, and one page is never the day. On 2026-09-17 a single page covered
  15:06-16:38 and the sweep judged that as the whole afternoon, while her
  16:47-17:13 messages in two DMs and a channel thread were never evaluated at
  all. Follow the `next_cursor` in `pagination_info` page by page until a page
  comes back with its newest message older than the window start, or the
  cursor ends. Pagination is also what makes either sort direction safe,
  because the gap a `limit` truncates is only fatal when nobody walks the
  cursor.
- **Group messages into conversations before judging anything.** A thread is
  every message sharing a `thread_ts` in one channel. A DM channel is one
  conversation for the whole window. Rank conversations by the newest message
  she sent in each and judge the conversation as a unit rather than message by
  message: five short DM replies are one exchange, a standalone channel post
  can be a work item even when it looks like chatter, and a conversation whose
  messages straddle a page boundary is one conversation, not two half-findings.
- Sent mail: the `superhuman-mail` MCP's `list_threads` with `labels: ["SENT"]`
  and `start_date` / `end_date` bracketing the window. The SENT label filter
  excludes drafts at the source, which matters because Jess writes in
  Superhuman and an abandoned draft carries her address as sender, looking
  exactly like a send. If a hit looks like a send but might not have left,
  confirm the label on the message before counting it.

**Bound BOTH ends of every Slack search, and check the timestamps that come
back.** A bare `after:` or an `on:<day>` is unbounded at the top: results come
back newest-first, so a `limit` truncates away the window and leaves only what
happened after it. The 21:06 scheduled sweep on 2026-09-16 asked for 19:06
onward and got messages stamped 21:51 and 22:06, none from its window, and
logged nothing while three real completions sat in the gap. Its own summary
said "returned stale results outside the window" and the run still reported
"nothing new". If a returned message falls outside the window asked for, the
filter did not apply: re-run it bounded rather than reading what came back.

Two details that decide whether the bounded form works. Slack's `after:` and
`before:` are EXCLUSIVE of the dates given, so covering today means
`after:<yesterday> before:<tomorrow>`; bracketing today between today and
tomorrow returns nothing and reads exactly like a quiet day. And pass
`sort_dir=asc` so the first page is the window's start rather than its newest
end; pagination is what actually fixes the truncation, and the bounded dates
are what keep the cursor from wandering outside the window.

### What is aimed at her

- `"<@UALHUAYEQ>" after:<since> before:<now>` in public and private channels. The `to:`
  modifier matches DMs only, never channel mentions. The pagination rule from
  "What Jess sent" applies here too: a mention search capped at one page reads
  the same silent truncation onto her asks.
- DMs: `to:me after:<since> before:<now>` with `channel_types=im,mpim`, paged
  the same way.
- Mail awaiting a reply: see the inbox triage below. It is its own step because
  the raw inbox is roughly 90 percent noise and reporting it unfiltered is worse
  than not reporting it at all.

### Inbox triage

A four-day inbox sample on 2026-09-09 held 60 messages. Five were real. Dumping
that list into the open buries the five, so this step exists to throw away the
other 55 and name only what a person is actually waiting on.

Pull with the `superhuman-mail` MCP's `list_threads`, which returns the recent
inbox with subject, sender, snippet, labels, and splits in one call, then
`get_thread` on anything that survives the drop rules. Thread ids are Gmail
ids, so the sweep and the dashboard mail section see the same objects.

Drop, in this order, and do not report what any rule removes:

1. **Calendar traffic.** Subject matching `invitation`, `updated invitation`,
   `accepted:`, `declined:`, `canceled`, `cancelled`, `RSVP`, or
   `Notification:`. The calendar is already its own section, and an invite is a
   duplicate of it rather than mail.
2. **Category labels and known newsletters.** `CATEGORY_PROMOTIONS`,
   `CATEGORY_UPDATES`, or `CATEGORY_SOCIAL` in the thread's labels, plus the
   recurring newsletter and vendor senders by name: TLDR, Health Tech Nerds,
   Fierce Healthcare, Substack, Alpha Signal, Morning Brew, beehiiv. The MCP
   does not return mail headers, so the old List-Unsubscribe rule became this
   one; when a newsletter slips through on a day, extend the sender list
   rather than going hunting for headers.
3. **Automated reports and receipts**, which are the ones the first two rules
   miss because they are transactional and personally addressed. Senders seen:
   `aptrinsic.com` (daily Applicant Activity, weekly Adoption), `stripe.com`
   receipts, `twilio.com` recharge notices, `fathom.video` digests,
   `notifications.usepylon.com` article-feedback notices, and Atlassian
   housekeeping. A machine sent it, nobody is waiting, so it does not appear.
   Two carve-outs that DO surface: a payment that actually failed, and a Pylon
   or Jira notice naming her as assignee or approver.
   Sub-rule that has already caught one false positive: a `[Superhuman]/AI/Respond`
   draft on a marketing or pitch thread is Superhuman's auto-draft, not her work
   in progress. A `has_draft` flag on vendor outreach never makes it waiting
   work; only a draft she composed does.

What survives gets one more test before it is reported. A message is real only
when a **person** sent it and it is **unresolved**, so check both:

- She is on the To line, not just Cc. Cc means the reply belongs to whoever was
  addressed, and treating it as hers manufactures work.
- Someone else spoke last. If her reply is the newest message in the thread, it
  is handled and it does not appear.
- Unread is the wrong filter either way. Anything that genuinely needs an answer
  has usually already been read.

Report the survivors as sender, what they want, and how long it has been
waiting. Five lines is a normal day. If the list runs past about eight,
something in the drop rules stopped working, so say so rather than printing the
inbox.

### Acting on mail

Anything that survives triage can be handled in the same pass, and each action
is hers to call:

- **Mark done:** `update_thread` with `mark_done: true`. That is Superhuman's
  own done, so the state stays coherent in the app instead of the thread only
  disappearing from Gmail.
- **Star:** `update_thread` with `mark_starred: true`, for keep-an-eye items.
- **Reply:** `create_or_update_draft` with `type: "reply"` and the thread id.
  The draft composes in her voice and lands in Drafts. Sending is a separate
  confirmed step and never happens from the sweep.

None of these run on a thread that has not been read end to end first; the
already-handled test above comes before any action.

### What she touched

- `GET http://localhost:8787/api/docs?days=1` on the dashboard covers Notion pages and local files
  she edited, with an edit count and timestamp. It reads the session
  transcripts under `~/.claude/projects`, so it already spans EVERY Claude
  session rather than the one you are in, and it catches files written through
  Bash as well as through Edit and Write. Work done in another window shows up
  here and nowhere else in this sweep.
- `ccvault search "<term>" after:<date>` for what she worked on in other Claude
  sessions. REQUIRED on every sweep, open and delta alike: she runs several
  Claude sessions in parallel, and this is the only query that sees them.
- Recent commits or PRs if a repo is in play: `gh search prs --author=@me`.
- **computer-usage** is the only source that sees work leaving no artifact at
  all. Beau's local tracker, SQLite at
  `~/Library/Application Support/computer-usage/usage.db`, dashboard on port
  9991. Query `app_sessions` for `app_name`, `window_title`, `browser_url`, and
  `keystroke_count` in the window. Never run the `computer-usage` binary to
  query it, since that is the tracking daemon and it will hang.

  **`start_time` is a REAL Unix epoch, not a datetime string.** Comparing it
  against `'2026-09-14 22:00:00'` returns zero rows and no error, which reads
  as a quiet night rather than a broken query. This has now cost two separate
  runs. Convert first, and copy the DB before reading it since the daemon
  holds it open:

  ```
  cp "$HOME/Library/Application Support/computer-usage/usage.db" /tmp/hc_usage.db
  SINCE=$(date -j -f "%Y-%m-%d %H:%M:%S" "2026-09-14 22:25:00" +%s)
  sqlite3 -header -column /tmp/hc_usage.db "
    SELECT app_name, SUM(keystroke_count) ks, SUM(click_count) clicks,
           COUNT(*) n, datetime(MAX(start_time),'unixepoch','localtime') last
    FROM app_sessions WHERE start_time >= $SINCE
    GROUP BY app_name ORDER BY ks DESC LIMIT 15;"
  ```

  A zero result is not evidence of a quiet window until the query is proven
  able to return a hit. Re-run without the `WHERE` and confirm a non-zero row
  count before reporting that nothing happened.

  What it is FOR is the gap between effort and artifact. Heavy keystrokes in a
  Slack channel with no message posted in that channel means something was
  typed and abandoned in the composer, which is the same failure as an unsent
  Superhuman draft and just as invisible. On 2026-09-03 it caught 282
  keystrokes across six minutes in a dev-partner channel that never produced a
  single message. Cross-check any app with real input against what that app
  actually published before deciding nothing happened.

  Time-per-app is NOT evidence of a completed thing, so never log a cat from it
  alone. It tells you where to go looking and what to ask her about.

### Grain

Check Grain for calls that happened since the last sweep, since a call is often
where a commitment gets made. `list_meetings` returns a summary inline, which is
usually enough; `search_in_transcripts` when looking for a specific topic. Fathom
covers a different set of calls, so a clean miss in one is not absence.

### Completeness gate - fill this before judging anything

Every source in Step 4 gets a row in this table, and the sweep is not allowed
to move to Step 4b until every row reads complete. Write the table out (or
state each row) before producing any findings.

| Source | Complete when | Evidence to have |
|---|---|---|
| Slack from: search | Cursor walked until a page's newest message is older than the window start, or the cursor ends | Say how many pages and the oldest timestamp seen |
| Slack mention search | Same cursor walk, same proof | Same |
| Slack DMs (to:me) | Same cursor walk, same proof | Same |
| Mail triage | Full `list_threads` read past the first screen; `next_cursor` followed or absent | State whether a cursor remained |
| `/api/docs` | FULL list read, not an excerpt | Save to a file and parse it (`curl ... > /tmp/hc_docs.json` then jq/python). A `head -c` or a partial print of this feed is a truncated read: on 2026-09-28 the first 3,000 characters cut off half a day of work, including a mockup build and a copyedit pass |
| ccvault | Searched for the window, results read | This is REQUIRED, not optional. It is the only source that names the parallel Claude sessions and says what each one was doing. On 2026-09-28 it was skipped, so the longevity article session and the pipeline session went unseen until Jess pointed at them |
| computer-usage | Query run with epoch-converted `start_time`, and a known-hit control if zero rows | Per the epoch rule above |
| Grain | `list_meetings` for the window | One call |

Three failure shapes this gate exists to stop, all from real runs:

1. **Page one read as the whole window.** Slack search returns newest-first at
   20 per page, so a single page covers only the most recent stretch. On
   2026-09-28 one page reached back to 13:52 and the sweep reported a "ton"
   of missing morning work; the cursor was sitting right there in
   `pagination_info` and was never followed.
2. **A truncated feed read as the full list.** The `/api/docs` response is a
   single JSON blob that pastes long. Slicing it with `head -c` or reading the
   inline preview drops entries from the middle and end without any visual
   sign.
3. **An optional source treated as skippable.** ccvault was listed as "useful
   when work landed in a repo or a doc". It is always that. Every session she
   runs in parallel is work, and this is the only query that sees them.

If a row cannot be completed (a tool is down, an API errors), say so in the
report rather than leaving the row silent. A silent row looks identical to a
checked one.

## Step 4b: Judge the evidence

For every signal, decide which bucket it lands in. This is the part that makes
the skill worth running.

**Completed, strong evidence.** Log it without asking. Strong means the artifact
exists and is public: a Slack message posted, an email with the `SENT` label, a
Notion page published, a PR merged, a task closed in Google Tasks. Log through
the dashboard so it earns its cat: `POST /api/done {"text": "..."}` for work that
was never a task, or `POST /api/task/<id>/complete` for one that was.

**Completed, weak evidence.** Ask before logging. Weak means the signal is
consistent with the work being done but does not prove it: a Superhuman draft, a
thread she replied in without resolving, a doc edited but not shared, a branch
pushed with no PR. A draft reply to a partner inquiry was once logged as a sent
reply on exactly this mistake. Superhuman drafts are the common case rather than
the exception, since she composes there and an abandoned draft can sit for days
looking like finished work.

**Date every draft before saying anything about it.** The mailbox holds a
standing pile of old drafts, so a raw count says nothing about today. Only a
draft tied to the sweep window is evidence of anything. The `superhuman-mail`
`list_drafts` rows carry no creation date, so date a draft through the thread
it belongs to (`get_thread` shows when the conversation last moved) or ask her.
On 2026-09-15 a pile of 19 drafts was reported as open work off an unchecked
count when exactly one was from the previous day.

The related trap is inferring a link between two signals because they turned
up in the same sweep. Heavy Superhuman keystrokes plus a pile of drafts looks
like a story, and in that run the keystrokes had actually produced a sent
reply while the drafts were years old. Check the timestamps on both sides
before claiming one caused the other, or report them as two separate facts.

**Already handled.** Read the thread before surfacing an ask. On 2026-09-02, five
of nine apparent asks were already answered by the time the sweep ran, and
reporting them as open made the list noise instead of signal.

Reading it means reading every message, not skimming for her name. Before
calling anything an ask on Jess, answer three questions from the text: who is
it addressed to, who said the part being attributed, and has anyone replied
since. On 2026-09-15 a thread aimed at Beau was reported as an ask on her,
with a sentence attributed to Beau that he never wrote, because her name was
mentioned once in the last message. A mention is not an ask, and someone
guessing that her permission might be needed is not the same as being asked
for it. When the ask is really aimed at someone else, say so plainly or leave
it out.

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

The day file is `~/.herding-cats/daily/YYYY-MM-DD.md`, one per day. The app
creates it on the first `/api/state` read of the day, so it usually exists
before you look, and `GET /api/dayfile` returns today's body as `{"markdown":
"..."}` without touching disk.

**Do not write it by hand and do not go looking for it under
`~/tools-and-projects/rosie/daily/`.** A stale directory of the same shape
lives there from an older layout, with real files in it that stop partway
through this month. Reading that one instead has already produced a wrong
answer: its newest file was a day behind, which looked exactly like the app
having failed to open the day.

The live root is whatever `HERD_HOME` points at, defaulting to
`~/.herding-cats`. Confirm with `GET /api/dayfile` rather than assuming a path.

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
  --params '{"tasklist":"MTcyMDI1NTI0MzQxNTIyMzI4ODM6MDow","task":"<taskId>"}' \
  --json '{"status":"completed"}' --format json
```

Never mark a task complete on inference. Working on something in this session is not the same as having finished it.

For anything that did not get done, offer to reschedule rather than leaving it to go overdue.

## Rules

- **Never publish.** No Notion page, no Slack message, nothing anyone else can see. The file this skill writes is the local day file in `~/.herding-cats/daily/`, a private working record only she can see. If Jess wants something written up for other people, that is a separate confirmed step through whichever skill owns that output.
- **Write the day file as you go.** Appending a decision the moment it lands takes one line. Reconstructing the day at 6pm is the thing that killed the last two attempts at this.
- **Log each completion when it happens, not in an evening batch.** This is the
  rule that decides whether the herd is worth having, and it is the one that
  has quietly stopped being followed. Through 2026-09-08 and 09-09 cats landed
  at six or more separate points across the day, 37 each. From 09-10 onward
  every cat arrives in two or three dumps and the daily count sits near 10,
  with nothing at all logged through `/api/done` since 09-09. Nothing about
  the work changed; what changed is that a 14-hour day now gets reconstructed
  from memory at 8pm, and whatever is not remembered then is simply gone.
  Anything finished mid-session gets logged in that moment, before moving to
  the next thing.
- **Never batch-create tasks.** Discovered todos are suggestions until Jess says
  to capture them. Completions are the opposite: log strong evidence without
  asking, because the friction of confirming twenty items is what stops the
  record being kept at all.
- **Log through the dashboard, not the day file alone.** `POST /api/done` earns
  the cat and writes the day file in one call. Writing the file by hand skips
  the pile, which is the part she looks at.
- **Never print the inbox.** Mail is reported only after the triage drop rules
  run, and a rule that removes something removes it silently. A four-day sample
  was 60 messages and 5 real, so an unfiltered list is not a shortcut, it is a
  worse answer than saying nothing. The same holds for a `gws` call that returns
  empty: confirm the subcommand ran before believing a quiet inbox.
- **Verify before believing a signal.** A mail search that does not filter on
  the `SENT` label returns her Superhuman drafts alongside real sends, so
  filter on `SENT` instead. A task can be completed on a phone. An ask in a
  thread may already be answered three replies down. Read the artifact, not
  the notification.
- **A delta sweep still covers every source, just over a shorter window.**
  Dropping sources rather than narrowing the window is what makes a re-run miss
  things, and the two most often dropped are the ones that need it least:
  `/api/docs` and computer-usage are single calls and they are the only view of
  work done in another window or another session. A re-run that checks mail,
  Slack, and tasks alone will report a quiet hour that was not quiet. This has
  already happened.
- **No truncated read counts as a source.** The completeness gate above is the
  enforcement: every source needs either a walked cursor or a fully parsed
  list, and a partial read of a paginated API is not evidence of anything. On
  2026-09-28 the sweep reported from page one of Slack plus a 3,000-character
  slice of `/api/docs`, Jess corrected it ("I've done a ton more than that"),
  and the full pass found eleven more completions. The gate was added so that
  correction cannot be needed twice.
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
