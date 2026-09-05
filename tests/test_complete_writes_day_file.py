"""Completing a task in the UI must reach the day file, not just the herd.

On 2026-09-04 seven completions logged through the dashboard earned cats and
never appeared in the day file, so the file's newest line sat hours behind the
real herd, and a later session reading it derived the wrong catch-up window.

The route pairs cats.earn with state.append_done. These cover that pairing:
earn awards once and refuses a duplicate, and append_done is what the route
calls only when a cat was genuinely awarded.
"""

from app import cats, state


def test_earn_alone_does_not_touch_the_day_file():
    """The gap the bug lived in. earn writes the herd and nothing else."""
    cats.earn("Kodexo: create Slack channel")
    assert "Kodexo: create Slack channel" not in state.day_file()


def test_append_done_puts_the_work_in_the_day_file():
    state.append_done("Kodexo: create Slack channel")
    assert "Kodexo: create Slack channel" in state.day_file()


def test_the_appended_line_is_marked_done():
    state.append_done("Ship the thing")
    line = next(l for l in state.day_file().splitlines() if "Ship the thing" in l)
    assert line.strip().startswith("- [x]")


def test_earn_refuses_a_duplicate_so_the_route_skips_the_second_append():
    first = cats.earn("Same work")
    second = cats.earn("Same work")
    assert first["cat"] is not None
    assert second["cat"] is None and second["duplicate"] is True


def test_pairing_earn_and_append_leaves_both_in_agreement():
    """What the route now does end to end."""
    earned = cats.earn("Deploy Navigator")
    if earned.get("cat"):
        state.append_done("Deploy Navigator")

    day = state.working_day()
    in_herd = any(c["for"] == "Deploy Navigator" for c in cats._load()["days"][day])
    assert in_herd
    assert "Deploy Navigator" in state.day_file()
