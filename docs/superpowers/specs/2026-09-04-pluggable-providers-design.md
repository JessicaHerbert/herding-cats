# Pluggable providers, portable config, and first-run setup

Status: approved design, not yet implemented
Date: 2026-09-04

## Problem

The app only runs for one person. Cloning it gets you someone else's
timezone, someone else's directory layout, and a hard requirement on
Google Tasks and Gmail reached through the `gws` CLI.

Four things are hardcoded:

- `TZ = ZoneInfo("America/Indiana/Indianapolis")` in `app/state.py`
- `DAILY_DIR = ~/tools-and-projects/rosie/daily`, a path that exists on
  one machine
- Google Tasks as the only task source, via `gws` subprocess calls
- Gmail as the only mail source, same route

`herd.json` and `picks.json` also live inside the checkout, so the data
sits in the repo folder and a fresh clone starts empty with no way to
bring history along.

## Goals

Someone who clones the repo can run it against their own task manager
and mail, on their own schedule, without editing source. Existing data
migrates rather than being abandoned. The dashboard is fully usable
without the Claude Code skill.

## The skill is not a wrapper

Worth stating plainly, because it changes what "portable" means here.
The repo is two products: a dashboard that stands on its own, and an
optional agent integration layered on top.

The skill sweeps Slack, Gmail, Notion, and call recordings, then judges
whether each signal is a completion, something still owed, or already
handled. No provider abstraction substitutes for that, and it requires
Claude Code, which most people cloning a cat app will not have.

Two endpoints currently have no UI at all, because the skill is what
calls them:

- `POST /api/done`, which logs work that was never a task and earns a
  cat. This is the core loop, so without a UI the app is broken for
  anyone skill-less.
- `POST /api/task`, which creates a task.

Both are addressed below. Everything else the dashboard needs already
has UI: completing, picking, undoing, and notes.

## Non-goals

Calendar stays Google-only and becomes optional. Todoist has no
calendar and a markdown file has no calendar, so the dashboard degrades
to no-calendar rather than growing a calendar abstraction that two of
three providers cannot satisfy.

No hosted sync, no multi-user support, no web-based OAuth flow. This
stays a local single-user app.

## Design

### Provider seam

The interface already exists implicitly. `state.tasks()` returns a
normalized dict and `mail.waiting()` returns a normalized row list;
neither caller knows anything about Google. The protocols codify the
shape that is already there.

```
app/providers/
  __init__.py      resolve from config, cache the instance
  base.py          TaskProvider, MailProvider protocols
  google_tasks.py  current gws code, moved
  todoist.py       REST
  localfile.py     tasks from a markdown file
  gmail.py         current mail.py code, moved
```

`TaskProvider`:

- `list_tasks() -> dict` with keys `picked`, `due_today`, `overdue`,
  `undated`, `done_today`; each row carries `id`, `title`, `due`,
  `notes`, and `completed` on done rows
- `complete(task_id) -> dict`
- `uncomplete(task_id) -> dict`
- `create(title, notes="", due=None) -> dict` returning at least `id`

`MailProvider`:

- `waiting(limit=40) -> list[dict]` with `id`, `from`, `subject`,
  `when`, `sort`, `snippet`, `url`, `unread`

Both protocols also expose `name` and a `check() -> tuple[bool, str]`
used by the wizard and the doctor path to verify credentials before
writing config.

`localfile` is the honesty test for the interface. It has no auth, no
network, and no server-assigned IDs, so it cannot inherit a Google
assumption without the abstraction visibly breaking. Task IDs there are
a stable hash of the line text.

Calendar becomes `providers.calendar_or_none()`. When the configured
task provider is not Google, or Google auth is absent, it returns
`None` and the dashboard renders without the calendar column rather
than erroring.

### Paths and config

`app/paths.py` resolves one root, `HERD_HOME`, defaulting to
`~/.herding-cats/`. Everything derives from it:

```
~/.herding-cats/
  config.toml
  herd.json
  picks.json
  daily/YYYY-MM-DD.md
```

`config.toml`:

```toml
[general]
timezone = "America/Indiana/Indianapolis"   # default: system tz
day_starts_at = 6                            # default: 6

[tasks]
provider = "google"                          # google | todoist | localfile
tasklist = "..."                             # google only
# token  = "..."                             # todoist only
# path   = "~/.herding-cats/tasks.md"        # localfile only

[mail]
provider = "gmail"                           # gmail | none
address = "you@example.com"
```

Read with stdlib `tomllib`, no new dependency. The wizard writes a flat
TOML by hand rather than adding a serializer.

Existing `HERD_TASKLIST` and `HERD_EMAIL` env vars keep working as
overrides, so the current setup does not break on upgrade.

Timezone defaults to the system zone. `day_starts_at` stays 6 by
default; the 6am boundary is the app's opinion, but a night shift or a
4am start is a legitimate different opinion.

`DAY_STARTS_AT` and `TZ` stop being module constants and become
config reads. `working_day()` and `_completed_date()` already funnel
every date decision through those two values, so this is a change at
one point rather than throughout.

### Migration

Live data exists: 108 cats, several daily files, and picks. On first
run after upgrade, if `~/.herding-cats/` is absent and the old
locations are present, the wizard offers to move them:

- `<repo>/herd.json` -> `~/.herding-cats/herd.json`
- `<repo>/picks.json` -> `~/.herding-cats/picks.json`
- `~/tools-and-projects/rosie/daily/` -> `~/.herding-cats/daily/`

Copy first, verify the copy parses and the cat count matches, then
remove the original. Never a bare move, so a failure midway leaves the
original intact.

### Setup wizard

`python -m app.setup`, run automatically when `config.toml` is missing.

1. Detect system timezone, show it, accept or override
2. Day start hour, default 6
3. Task provider: google, todoist, or localfile
   - google: list task lists via `gws`, pick one; if `gws` is missing
     or unauthenticated, say exactly that and how to fix it
   - todoist: prompt for an API token, verify with a live call
   - localfile: prompt for a path, create the file with a short header
     if absent
4. Mail provider: gmail or none
   - gmail: confirm the address, verify with a live call
5. Run `check()` on each chosen provider before writing anything
6. Offer migration if old data is found
7. Write `config.toml`, print where it went

Every credential prompt verifies before persisting, so a typo surfaces
at setup rather than as an empty dashboard later.

### Standalone UI

Two small additions to `web/`, both against endpoints that already
exist and are exercised by the skill, so no backend change is needed.

- **Log something done.** An input that posts `{"text": ...}` to
  `/api/done` and earns a cat on submit. This is the path that records
  work which was never a task, and it is the reason the app exists.
- **Add a task.** An input that posts `{"title": ...}` to `/api/task`,
  routed through the configured task provider.

Both follow the existing UI idiom: delegated click handlers and a
prompt-style entry, matching how notes already work, rather than
introducing a new form system for two fields.

The `localfile` provider makes the add-task path meaningful without any
account, so the two features land together.

### Portability of language

`skill/SKILL.md` is written about one person by name, and it references
a specific Slack, Notion, and Grain setup. It stays as it is, in that
voice, presented as a real working example rather than a template.
Genericizing it would produce mostly placeholders and lose the thing
that makes it worth reading.

`README.md` leads with the standalone app: setup, providers, and how to
add your own. The skill gets its own clearly marked section as an
optional Claude Code integration, stating up front that it needs Claude
Code and describing what it adds, so nobody mistakes it for a
requirement.

Module docstrings and comments in `app/` change to second person or
neutral phrasing.

## Testing

- Protocol conformance: one test parameterized across all three task
  providers, asserting the returned shape. `localfile` runs in CI with
  no credentials; google and todoist skip when unconfigured.
- `localfile` end to end against a temp file: create, complete,
  uncomplete, list.
- Config resolution: defaults when no file, env override precedence,
  bad TOML producing a clear error rather than a traceback.
- Day boundary: `working_day()` across the configured hour, and with a
  non-default `day_starts_at`, including the existing 6am regression.
- Migration: fixture with old-layout data, assert cat count and daily
  file count survive, assert originals removed only after verification.
- The existing duplicate-cat regression keeps running.
- Skill-less path: with `localfile` configured and no skill present,
  logging done work earns a cat and adding a task appears in the list.
  This is the check that the app stands alone.

## Sequencing

Each step leaves the app working:

1. `paths.py` and `config.py`, with everything still defaulting to
   current behavior
2. Migration, so data moves before providers change under it
3. `providers/base.py` and `google_tasks.py` + `gmail.py` as moves of
   existing code, no behavior change
4. `localfile` provider, which proves the seam
5. `todoist` provider
6. Timezone and `day_starts_at` become config reads
7. Standalone UI for logging done work and adding a task
8. Setup wizard
9. README and docstring pass

## Risks

Moving `herd.json` out of the checkout touches live data with no
backup discipline beyond what migration does itself. Mitigated by
copy-verify-delete and by the fact that the file is already gitignored,
so no history exists to fall back on.

`gws` is a personal CLI, not a public dependency. The Google provider
should state that plainly and fail with a useful message rather than a
subprocess error, since most people cloning this will not have it.
