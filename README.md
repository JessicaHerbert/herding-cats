# herding cats

A day opener that turns finished work into a collectible.

It reads the task list and calendar you already use, puts the day on one screen,
and gives you a procedurally drawn cat every time you finish something. The cats
accumulate into a herd you can look back through. Rare coats are actually rare.

Built for one person. The constants are at the top of `app/state.py` and there
are only a few of them, so forking it and pointing it at your own list takes a
couple of minutes.

## Why it exists

Task apps are good at showing what is left and bad at showing what you did. On a
day where you close fifteen things, the reward for finishing the fifteenth is an
empty list, which is the same thing you would have seen if you had finished none
of them.

So the pile grows instead. Every completed task earns a cat that stays on the
screen for the rest of the day and in the history forever. The list still tells
you what is left; the pile tells you what happened.

## What is on the screen

**The pile** is today's cats, stacked in rows. Hover one for the task that
earned it.

**Today** is the calendar, with the current meeting highlighted.

**Tasks** splits into what you picked for today, what is genuinely due, and the
undated backlog. Starring a task pulls it into Today without inventing a fake
due date, which is the thing that makes a backlog rot.

**Done** is what closed today, newest first, each with an undo.

**Waiting on you** is email where someone else spoke last and you are on the To
line rather than Cc. Unread is the wrong signal: the mail that needs a reply has
usually been read, and what is left unread is notifications.

**Watching** is pulled from a `## Watching` section in a local day file, for
things that are not tasks but are not nothing either.

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

The one design decision worth stealing: **a trait that is rolled must be stored,
not recomputed.**

Coats and traits started as pure functions of the task text, computed in the
browser at render time. That works and it is stable, right up until you add a
coat or retune the odds, at which point every cat you have ever earned silently
changes appearance. A rare one you remember earning becomes a common one, and
there is no record it was ever otherwise.

They are rolled server-side and written into the record now. Retuning the odds
changes what future cats get and leaves history alone. Porting the roll from
JavaScript to Python meant matching `Math.imul` semantics exactly, which is worth
a parity test against every existing record before backfilling.

## The skill

`skill/SKILL.md` is a [Claude Code](https://claude.com/claude-code) skill that
opens the day and catches you up on it. It reads tasks and calendar, flags
collisions, and keeps a day file in markdown that the dashboard reads back.

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

The day file is written at the open and appended to as things happen. Two earlier
attempts at the same idea wrote it at the end of the day and both died, because
the end of the day is when there is the least appetite for writing anything down.

## Running it

```
uv sync
uv run uvicorn app.main:app --port 8787
```

Then open `http://localhost:8787`. It expects the
[`gws`](https://github.com/) Google Workspace CLI on your PATH and authenticated,
for Tasks, Calendar, and Gmail.

To point it at your own data, set `TASKLIST` and `TZ` in `app/state.py`. Get your
list id with `gws tasks tasklists list`.

`herd.sample.json` shows the shape of a herd. Copy it to `herd.json` to see a
populated dashboard before you have earned anything.

## What is not here

`herd.json` and the day files are gitignored. Cat labels are real task text, which
on any working day names customers, colleagues, and partners. The herd is the
whole point of the app and it is also the part that cannot be published.

## Credits

Cats by [cat-snacks](https://github.com/beaugunderson/cat-snacks). Names trained
on [Seattle pet licenses](https://data.seattle.gov/Community/Seattle-Pet-Licenses/jguv-t9rb),
which is a genuinely delightful public dataset.
