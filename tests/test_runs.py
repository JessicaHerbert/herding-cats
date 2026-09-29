"""The sweep run log.

Cost and the per-model split exist only on the CLI's final result event and
appear nowhere in the session transcript, so a run not captured at the time
can never be priced afterwards. These pin the capture and the arithmetic.
"""

import json

from app import paths, runs


def test_empty_log_reads_as_empty(tmp_home):
    assert runs.read() == []
    s = runs.summary()
    assert s["today"]["runs"] == 0
    assert s["today"]["cost_usd"] == 0


def test_record_round_trips(tmp_home):
    runs.record(trigger="schedule", logged=2, cost_usd=1.602, duration_ms=148397,
                models={"claude-haiku-4-5-20251001": {"cost_usd": 0.2487},
                        "claude-opus-5[1m]": {"cost_usd": 1.3533}})
    rows = runs.read()
    assert len(rows) == 1
    assert rows[0]["trigger"] == "schedule"
    assert rows[0]["logged"] == 2
    assert rows[0]["cost_usd"] == 1.602


def test_model_names_collapse_to_families(tmp_home):
    """A version suffix in the key splits one series into two the day a
    model rolls, which makes any trend across the boundary wrong."""
    runs.record(trigger="button", logged=0,
                models={"claude-haiku-4-5-20251001": {"cost_usd": 0.1},
                        "claude-opus-5[1m]": {"cost_usd": 0.2}})
    assert set(runs.read()[0]["models"]) == {"haiku", "opus"}


def test_newest_first(tmp_home):
    runs.record(trigger="button", logged=1)
    runs.record(trigger="schedule", logged=2)
    assert [r["logged"] for r in runs.read()] == [2, 1]


def test_summary_totals_cost_and_splits_by_model(tmp_home):
    runs.record(trigger="schedule", logged=1, cost_usd=1.60,
                models={"claude-opus-5[1m]": {"cost_usd": 1.35},
                        "claude-haiku-4-5-20251001": {"cost_usd": 0.25}})
    runs.record(trigger="button", logged=3, cost_usd=0.40,
                models={"claude-opus-5[1m]": {"cost_usd": 0.40}})

    t = runs.summary()["today"]
    assert t["runs"] == 2
    assert t["cats"] == 4
    assert t["cost_usd"] == 2.0
    assert t["by_model"]["opus"] == 1.75
    assert t["by_model"]["haiku"] == 0.25


def test_unpriced_run_counts_but_does_not_skew_cost(tmp_home):
    """A crashed run may report no cost. Treating that as zero would
    understate spend silently."""
    runs.record(trigger="schedule", logged=0, error="boom")
    runs.record(trigger="schedule", logged=1, cost_usd=1.0)

    t = runs.summary()["today"]
    assert t["runs"] == 2
    assert t["priced"] == 1
    assert t["cost_usd"] == 1.0


def test_a_failed_run_is_still_recorded(tmp_home):
    runs.record(trigger="schedule", logged=0, error="claude exited nonzero")
    assert "claude exited" in runs.read()[0]["error"]


def test_malformed_line_is_skipped_not_fatal(tmp_home):
    runs.record(trigger="button", logged=1)
    with paths.runs_file().open("a") as fh:
        fh.write("{half written\n")
    runs.record(trigger="button", logged=2)

    rows = runs.read()
    assert len(rows) == 2, "a torn line must not take the panel down"


def test_log_stays_bounded(tmp_home):
    for i in range(runs.MAX_LINES + 25):
        runs.record(trigger="schedule", logged=i)
    lines = paths.runs_file().read_text().splitlines()
    assert len(lines) <= runs.MAX_LINES


def test_append_only_never_rewrites_history(tmp_home):
    runs.record(trigger="button", logged=1, cost_usd=0.5)
    first = json.loads(paths.runs_file().read_text().splitlines()[0])
    runs.record(trigger="schedule", logged=9, cost_usd=9.9)
    still = json.loads(paths.runs_file().read_text().splitlines()[0])
    assert first == still
