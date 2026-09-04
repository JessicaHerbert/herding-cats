# herding cats

A day opener that turns finished work into a collectible.

It reads the task list you already use, puts the day on one screen, and gives
you a procedurally drawn cat every time you finish something. The cats
accumulate into a herd you can look back through. Rare coats are actually rare.

## Why it exists

Task apps are good at showing what is left and bad at showing what you did. On a
day where you close fifteen things, the reward for finishing the fifteenth is an
empty list, which is the same thing you would have seen if you had finished none
of them.

So the pile grows instead. Every completed task earns a cat that stays on the
screen for the rest of the day and in the history forever. The list still tells
you what is left; the pile tells you what happened.

## Install

You need Python 3.11 or newer and [uv](https://docs.astral.sh/uv/). Nothing
else is required to get a working dashboard.

```
git clone <this repo>
cd herding-cats-app
uv sync
```

`uv sync` creates `.venv/` and installs the dependencies into it, including
pytest, since uv installs the `dev` dependency group by default. Every command
below uses `.venv/bin/python` rather than a bare `python3`, because a bare
`python3` will not have FastAPI or uvicorn on its path.

## Setup

Run the wizard once. It asks which task list to read, verifies that the answer
actually works before saving anything, and writes the config file for you.

```
.venv/bin/python -m app.setup
```

The wizard asks for your timezone, the hour your day starts at, a task
provider, and a mail provider. When it finishes it prints the path of the
config file it wrote, which is `~/.herding-cats/config.toml` unless you have
set `HERD_HOME`.

Two of its questions are worth knowing about before you answer them. The
timezone it offers as a default comes from your system and can come back as an
abbreviation such as `EDT`, which is not a zone the app can load, so type a
full IANA name like `America/New_York` if the default is not one. It also asks
whether to move in data from an older layout of this app, but only when it
finds some, so the wizard does not always ask the same number of questions.
Answer `n` to that one unless you are upgrading an install you recognize.

If you want the fastest possible start with no accounts involved, choose the
local markdown file provider and then choose "None" for mail. The wizard
creates the task file for you if it is not there yet.

## Running it

```
.venv/bin/uvicorn app.main:app --port 8787
```

Then open `http://localhost:8787`. On macOS you can also run
`.venv/bin/python window.py`, which starts the same server and puts it in a
native window with its own Dock icon.

The app refuses to start until the config file exists, and it tells you to run
the wizard rather than guessing at defaults. You do not need Claude Code or any
other agent to use it. The `+ done` button logs something you finished and
earns a cat for it, and the `+ task` button adds a task to whichever provider
you configured.

## Task providers

Pick one of these three. The wizard writes the choice into `[tasks]` in the
config file.

| Provider | What it reads | What it needs |
| --- | --- | --- |
| `google` | Your Google Tasks list, plus your Google Calendar | The `gws` CLI on your PATH, authenticated against your Google account |
| `todoist` | Your Todoist tasks over the v1 REST API | A Todoist API token, from Todoist's integrations settings |
| `localfile` | A markdown file of `- [ ]` lines that you own | Nothing at all |

The `gws` CLI the Google provider shells out to is a personal Google Workspace
command line tool rather than a published package, so it is not something you
can install from this repo. If you do not already have it, one of the other two
providers is the better path. The Google provider expects `gws tasks tasklists
list`, `gws tasks tasks list`, and `gws calendar events list` to work from your
shell.

Calendar is Google's alone. With `todoist` or `localfile` the dashboard simply
has no calendar column rather than showing an empty one.

The local file format is one task per line. A due date is optional and goes in
parentheses at the end of the line.

```markdown
# Tasks

- [ ] Write the migration note
- [ ] Reply to the vendor thread (due 2026-09-08)
- [x] Ship the config reader (done 2026-09-04)
```

## Mail providers

Mail powers the "Waiting on you" panel, which lists threads where someone else
spoke last and you are on the To line rather than Cc. Unread is the wrong
signal here, because the mail that needs a reply has usually been read and what
is left unread is notifications.

| Provider | What it reads | What it needs |
| --- | --- | --- |
| `gmail` | Your Gmail threads through the `gws` CLI | The same authenticated `gws` CLI the Google task provider uses, plus your own address |
| `none` | Nothing, and the panel stays empty | Nothing |

## Config reference

The config file lives at `~/.herding-cats/config.toml`. The wizard writes it,
and you can edit it by hand afterwards. Keys that do not apply to your chosen
provider are left out rather than written empty.

```toml
[general]
timezone = "America/New_York"
day_starts_at = 6

[tasks]
provider = "localfile"
path = "/Users/you/.herding-cats/tasks.md"

[mail]
provider = "none"
```

| Section | Key | Meaning | Default |
| --- | --- | --- | --- |
| `general` | `timezone` | An IANA timezone name, used for every date the app computes | Your system timezone |
| `general` | `day_starts_at` | The hour, 0 to 23, at which a new working day begins | `6` |
| `tasks` | `provider` | One of `google`, `todoist`, or `localfile` | `google` |
| `tasks` | `tasklist` | The Google Tasks list id, used by `google` only | empty |
| `tasks` | `token` | The Todoist API token, used by `todoist` only | empty |
| `tasks` | `path` | The markdown file to read, used by `localfile` only | empty |
| `mail` | `provider` | Either `gmail` or `none` | `gmail` |
| `mail` | `address` | Your own email address, used by `gmail` to tell who spoke last | empty |

Two environment variables still override the file, because they were the
original settings and an older installation should keep working. `HERD_TASKLIST`
overrides `tasks.tasklist` and `HERD_EMAIL` overrides `mail.address`.

### The day boundary

`day_starts_at` defaults to 6, which means work you finish at 00:30 files under
the previous day rather than a fresh one nobody has started yet. This is the
most surprising behavior in the app and it is deliberate: a day that turns over
at midnight splits one late working session into two, so the pile you built up
that evening disappears while you are still looking at it. Set it to `0` if you
would rather have a calendar day.

## Where your data lives

Everything hangs off one root directory, so the app can be moved, reinstalled,
or cloned fresh without losing the herd. The root is `~/.herding-cats` unless
you set `HERD_HOME` to another path.

| Path | What it holds |
| --- | --- |
| `$HERD_HOME/config.toml` | The config described above |
| `$HERD_HOME/herd.json` | Every cat you have earned, by day |
| `$HERD_HOME/picks.json` | Which tasks you starred for which working day |
| `$HERD_HOME/daily/YYYY-MM-DD.md` | The day file, which holds the watchlist, notes, and anything logged as done |

Setting `HERD_HOME` is also how you keep a test run away from your real herd.
Export it before the command rather than piping through it, since a
`VAR=x cmd1 | cmd2` prefix does not survive past the pipe.

`herd.sample.json` in the repo shows the shape of a herd. Copy it to
`$HERD_HOME/herd.json` to see a populated dashboard before you have earned
anything.

## Adding your own provider

A provider is a plain class with a `name` attribute and a handful of methods.
There is no base class to inherit from, only the two protocols in
`app/providers/base.py` that describe the shape the rest of the app expects.

A task provider needs `check()`, which returns a `(bool, str)` pair saying
whether it is usable right now and what would fix it if not, along with
`list_tasks()`, `complete(task_id)`, `uncomplete(task_id)`, and
`create(title, notes, due)`. The `list_tasks()` return value is a dict with the
five keys in `base.BUCKETS`, each holding a list of rows built by
`base.task_row()`. A mail provider is smaller: it needs `check()` and
`waiting(limit)`, which returns the threads where the reply is yours to write.

`app/providers/localfile.py` is the shortest complete example and the one worth
copying, since it has no server, no auth, and no assigned ids, which means
nothing backend-specific can hide in it.

Three edits wire a new provider in. Write the class in `app/providers/`, add a
branch for it in `_resolve()` in `app/providers/__init__.py` and add its name to
`TASK_PROVIDERS` or `MAIL_PROVIDERS` in `app/config.py`, then add it to
`TASK_PROVIDER_MENU` or `MAIL_PROVIDER_MENU` and the matching `_make_*` factory
in `app/setup.py` so the wizard can offer it.

## Tests

```
uv sync --group dev
.venv/bin/pytest tests/
```

The suite points `HERD_HOME` at a scratch directory for every test through an
autouse fixture, so running it cannot reach a real herd.

## What is on the screen

**The pile** is today's cats, stacked in rows. Hover one for the task that
earned it.

**Today** is the calendar, with the current meeting highlighted. It appears
only with the Google task provider.

**Tasks** splits into what you picked for today, what is genuinely due, and the
undated backlog. Starring a task pulls it into Today without inventing a fake
due date, which is the thing that makes a backlog rot.

**Done** is what closed today, newest first, each with an undo.

**Waiting on you** is mail where someone else spoke last and you are on the To
line rather than Cc.

**Watching** is pulled from a `## Watching` section in the day file, for things
that are not tasks but are not nothing either.

**Herd history** is the last seven days, linking through to the full collection.

## The cats

Drawings come from [cat-snacks](https://github.com/beaugunderson/cat-snacks) by
Beau Gunderson, which draws a different cat for every seed. Seeding off the task
text means a given cat looks the same on every refresh.

On top of that:

**Twelve coats.** Eight common ones cycle by seed. Every tenth cat of the day is
gold, guaranteed. Three more are rolled per cat at 1 in 85, 1 in 340, and 1 in
1,200, tuned against a busy day so a rose is roughly weekly and a cosmic is
roughly quarterly.

**Traits.** Whiskers on about two thirds, glasses or a hat on about one in nine.

**Names.** Common cats get a name from a character-level Markov chain trained on
4,959 real cat names from Seattle's public pet license register. Order 3, because
order 2 is mush and order 4 memorizes the corpus. Every generated name is checked
against all 6,107 real ones and rejected if it collides, so no cat gets a name
that already exists. This produces Buffletches, Bogerald, Chiqueak, and
Hexachordal nonsense of exactly the right kind.

Rare cats do not get generated names. Seattle's register already contains better
ones than any model would invent, so a rare coat draws from the real absurdities
in the data: Doofenshmirtz Evil Incorporated, Grand Theft Auto: Vice Kitty, Eris
(Goddess of Chaos and Queen of Discord). A cosmic cat is always Beauregard Brown
Baddest Cat in Town, who is a real licensed cat in Seattle.

## Store what you roll

The one design decision worth stealing is that a trait which is rolled must be
stored rather than recomputed.

Coats and traits started as pure functions of the task text, computed in the
browser at render time. That works and it is stable, right up until you add a
coat or retune the odds, at which point every cat you have ever earned silently
changes appearance. A rare one you remember earning becomes a common one, and
there is no record it was ever otherwise.

They are rolled server-side and written into the record now. Retuning the odds
changes what future cats get and leaves history alone. Porting the roll from
JavaScript to Python meant matching `Math.imul` semantics exactly, which is worth
a parity test against every existing record before backfilling.

## What is not here

`herd.json`, `picks.json`, and the day files are gitignored and live outside the
repo entirely. Cat labels are real task text, which on any working day names
customers, colleagues, and partners. The herd is the whole point of the app and
it is also the part that cannot be published.

## Optional: the Claude Code skill

Everything above works on its own. This section is about an extra that needs
[Claude Code](https://claude.com/claude-code) installed, and you can skip it
entirely without losing the dashboard.

`skill/SKILL.md` is a Claude Code skill that opens the day and catches you up on
it. It is not a wrapper around this app's API. What it does is sweep the systems
you work in, judge what each signal means, and log the ones that count as
finished so they earn a cat without you clicking anything.

The part worth reading is the evidence sweep. Most finished work is not
task-shaped: it is a message you posted, a page you published, a handoff you
made. So the sweep looks at what you SENT rather than only what was sent to you,
across Slack, mail, Notion, past agent sessions, and call recordings, then sorts
every signal into completed-with-strong-evidence, completed-but-unproven,
already-handled, or genuinely-waiting.

Strong evidence gets logged without asking, because confirming twenty items one
at a time is how a record stops being kept. Weak evidence asks first: a `from:me`
mail search returns drafts, and a draft reply to a partner inquiry looks
identical to a sent one until you check the label.

Be aware that this file is one person's real working copy rather than a
template. It names the specific Slack workspace, Notion databases, and MCP
servers that person has connected, and it will not run as written against a
different setup. Read it as a worked example of the idea and rewrite the sweep
for your own systems.

## Credits

Cats by [cat-snacks](https://github.com/beaugunderson/cat-snacks). Names trained
on [Seattle pet licenses](https://data.seattle.gov/Community/Seattle-Pet-Licenses/jguv-t9rb),
which is a genuinely delightful public dataset.
