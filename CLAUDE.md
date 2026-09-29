# CLAUDE.md

## What this is

Herding Cats is a local dashboard that reads whichever task list you already
use, puts the day on one screen, and awards a procedurally drawn cat for every
task you finish. The cats accumulate into a herd stored on disk.

The dashboard is standalone and needs no agent: the `+ done` and `+ task`
buttons in the web UI cover logging work and adding tasks. `skill/SKILL.md` is
an optional Claude Code skill that sweeps other systems and judges what counts
as finished, and it is one person's real working copy rather than a template.

## Layout

| Path | What lives there |
| --- | --- |
| `app/` | The FastAPI backend. `main.py` is the routes, `state.py` the day logic, `cats.py` the herd, `config.py` and `paths.py` the settings and locations |
| `app/sweep.py` | The catch-up button: the prompt it sends, the tools it grants, and the cooldown. `agent.py` is the bridge to the `claude` CLI it runs through |
| `app/providers/` | The task and mail backends, with the protocols in `base.py` and resolution in `__init__.py` |
| `web/` | The frontend, served as static files by `app.main` |
| `skill/` | The optional Claude Code skill, excluded from the neutral-voice rules that apply to `app/` |
| `tests/` | pytest, run from the repo root |

## Commands

```
uv sync                                          # install into .venv/
uv sync --group dev                              # plus pytest
.venv/bin/python -m app.setup                    # first-run wizard
.venv/bin/uvicorn app.main:app --port 8787       # run the app
.venv/bin/python window.py                       # same, in a native macOS window
.venv/bin/pytest tests/                          # the whole suite
```

Always use `.venv/bin/python` and `.venv/bin/pytest`. A bare `python3` does not
have FastAPI, uvicorn, or pytest on its path and will fail with an import error
that looks like a code problem rather than an environment one.

## Setup and config

`app.main` refuses to import until a config file exists, and raises a
`SystemExit` telling you to run the wizard. Run
`.venv/bin/python -m app.setup` once. It writes `~/.herding-cats/config.toml`
with `[general]`, `[tasks]`, and `[mail]` sections. Every key is documented in
the config reference in `README.md`.

Task providers are `google`, `todoist`, and `localfile`. Mail providers are
`gmail` and `none`. Calendar is Google-only, so the other task providers simply
have no calendar column.

`HERD_HOME` moves the whole data root, which is how you run anything against
scratch data. Export it or put it inline on the single command, because a
`HERD_HOME=x cmd1 | cmd2` prefix does not survive past the pipe.

One prompt in the wizard still needs care. It offers to move in data from an
older layout, and the move deletes the originals once it has copied them. The
day-file half of that is now scoped: `migrate.find_old()` offers the fixed
path outside the repo only when `HERD_HOME` is at its default, so a throwaway
clone pointed at scratch is not shown someone's real notes. The herd and picks
files are still looked for beside the code, which is correct because they
follow the clone. Answer `n` unless you are deliberately upgrading an install
you recognize, and never answer it from a scripted or unattended run.

## Restarting actually restarts it

`window.py` starts uvicorn as a child and, until this was fixed, never stopped
it. The server outlived every quit, got reparented to launchd, and the reuse
check at startup then found it still answering and kept it, so quitting and
reopening the app could not pick up new code. One server ran for a day that way
and made a newly added route look broken rather than absent.

The window now stops any backend it started, through `atexit` and a `finally`
around `webview.start()`. A server it did NOT start is left alone, on the
assumption someone is running uvicorn by hand.

When a route 404s that the code clearly defines, check the server's age before
debugging the route:

```
ps -o lstart=,command= -p $(lsof -ti:8787)
```

A POST to a path the app does not serve returns 405 rather than 404, because
`StaticFiles` is mounted at `/` and answers GET only. Either status means the
route is missing, not that the handler is wrong.

## The catch-up button

The button runs the herding-cats skill headless through the `claude` CLI,
narrowed to the evidence sweep, and logs whatever cleared the strong-evidence
bar. Three things about it are not guessable from the code.

**A completion is counted from the herd, never from the reply.** Counting lines
in the agent's answer was the first attempt and it reported "13 logged" on a run
that logged nothing, because thirteen was how many lines the explanation ran to.

**`/api/done` does not award a cat.** It writes the day file and stops, and
`cats.sync_day_file()` awards the cat on the next state read. Anything counting
cats straight after a write has to sync first, or it sees zero. That mistake
made a sweep that found seven real completions report zero.

**Permission patterns match on the command prefix, so narrow ones miss.**
`Bash(curl -s -X POST http://127.0.0.1:8787/api/done:*)` looks precise and
refuses the same request the moment the agent orders its flags differently or
pipes the output. Three consecutive denials ended one run before it swept
anything. `allowed()` grants `Bash(curl:*)` for that reason. The alternative
considered and rejected was `--dangerously-skip-permissions`, which would let a
background process run anything at all.

Testing it means a scratch `HERD_HOME` and a spare port, never 8787, because a
sweep against the real dashboard writes real cats into the real herd.

## Never commit

`herd.json`, `picks.json`, `.env`, and any `herd.backup-*.json`. They are in
`.gitignore` already and they must stay there. Cat labels are the real text of
real tasks, which on any working day names customers, colleagues, and partners,
and this repo is public. There is no redaction pass that makes a herd safe to
publish, so the answer is that it never gets added.

The live data lives at `~/.herding-cats/` rather than in the repo. Treat that
directory as production: never write to, move, or delete `herd.json`,
`picks.json`, or `daily/` there. Point `HERD_HOME` at a path under `/tmp` for
any manual check.

## Adding a provider

Implement the `TaskProvider` or `MailProvider` protocol in
`app/providers/base.py`. There is nothing to inherit from, only the method
shapes. `app/providers/localfile.py` is the shortest complete example.

Register the new class in `_resolve()` in `app/providers/__init__.py`, add its
name to `TASK_PROVIDERS` or `MAIL_PROVIDERS` in `app/config.py` so the config
reader accepts it, then add it to the wizard's menu and matching `_make_*`
factory in `app/setup.py`.

## The 6am day boundary

`state.working_day()` subtracts a day when the current hour is below
`general.day_starts_at`, which defaults to 6. Work finished at 00:30 therefore
files under the previous day. This is the most surprising behavior in the
codebase and it is intentional, because a day that turns over at midnight
splits one late working session in two and the pile someone built that evening
vanishes while they are still looking at it.

Anything that groups by day goes through `state.working_day()` rather than
computing a date itself. That includes the herd, the picks file, the day files
in `daily/`, and the completed-task filters in every provider.

## Voice in this repo

Code comments and docstrings in `app/` use second person or a neutral subject
rather than naming a person. American spelling throughout. No em dashes or en
dashes anywhere, in code or docs; a regular hyphen is the substitute.
`skill/SKILL.md` is deliberately outside these rules and stays as it is.
