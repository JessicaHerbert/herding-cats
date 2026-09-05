# Backlog

Written 2026-09-04. Not built yet.

## What it is for

There is a category of work that sits between a task and a note. Jess has
decided it is worth doing and is not driving it. The Lifeworks case study is
the shape: real work, genuinely wanted, waiting on someone else to answer a
question, and nobody is pushing it.

A task with no due date sinks into the undated bucket. A Slack later disappears
the moment the list gets long. Both failure modes end the same way, which is
that the thing is still not done in six months. The backlog exists to hold that
work somewhere it can be found on purpose.

## What it is not

It is not a read-it-later pile. Every entry is work someone intends to do.

It is not part of the day. The day view answers what is happening now, and
mixing in work with no date is what makes a day view stop being scannable.

## Cats

A backlog item never earns a cat. A cat means something was finished, and a
backlog entry has no finish state.

Promotion is a fan-out rather than a status change. Acting on a backlog item
produces one or more real tasks, and those earn cats normally. "Dev partner
onboarding" produced ten tasks on 2026-09-04 and every one of them earned its
own cat.

The parent survives promotion. Keeping it is what makes a recurring shape
reusable, since the next dev partner needs the same ten steps.

## How an item comes back

Three routes, all of them pull. Nothing pushes.

1. A list on its own page, separate from the day view.
2. Asking for it directly.
3. Asking something loose like "what's on my list", which should reach the
   backlog as well as open tasks.

A periodic nudge was considered and rejected. Anything that interrupts turns
the backlog into another notification stream, and the whole point is that these
are things not being driven right now.

The risk this leaves is that an item is only seen when it is looked for, which
is how Slack laters fail. Route 3 is the mitigation, since a loose question is
asked far more often than a page is opened deliberately.

## Shape of an entry

- What the work is.
- Why it is waiting, when something specific is blocking it. The Lifeworks entry
  is waiting on a scope answer about whether the study covers the customer or
  the partner who built for them.
- Any position already taken, so it does not get re-litigated. On Lifeworks the
  stated preference is getting the partner to publish a plugin open source so
  they land on the certified page, with a customer-use-case study as the
  fallback.

## Worked example

Lifeworks case study. Raised in #phi-ops-summaries on 2026-09-04. Waiting on
Allison to confirm scope. Not being chased.

## Open questions

- Whether the backlog lives in Google Tasks behind a flag or in its own store.
  A flag is much less code and inherits sync for free; a separate store keeps
  the task list clean. Not decided.
- Whether Slack saved items should be a capture source, which would need the
  Slack read path wired up.
- Whether the backlog lives beside the watchlist in the UI or somewhere else.

## Relationship to the watchlist

The backlog does not replace the watchlist. They answer different questions.

The watchlist tracks state that keeps changing, so every line is a claim about
right now: is the job still failing, did the field get filled. That is why an
entry carries a last-checked time and gets classified good or bad, and why a
resolved line drops off at rollover.

A backlog entry has no state to re-check. The Lifeworks case study will not
change on its own, and there is nothing to verify about it between one look and
the next.

Worth noting separately that the watchlist is not being used. It only populates
when Claude writes a `## Watching` section into the day file, so it depends on
that happening rather than on anything the user does. Nothing wrote one on
2026-09-04. Whether that is a prompting problem or a sign the feature is not
wanted has not been established, and it should be answered before the backlog
is built, since a second section that fills only when Claude remembers would
fail the same way.
