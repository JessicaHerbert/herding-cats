import json
import time

from app import state, sweep


def test_no_previous_sweep_is_empty(tmp_home):
    assert sweep.last() == {}
    assert sweep.cooling() == 0


def test_record_then_read_back(tmp_home):
    sweep.record(3, "posted the announcement")
    got = sweep.last()
    assert got["logged"] == 3
    assert got["summary"] == "posted the announcement"
    assert got["clock"]


def test_cooldown_blocks_then_expires(tmp_home):
    sweep.record(1, "x")
    assert 0 < sweep.cooling() <= sweep.COOLDOWN

    stale = json.loads((tmp_home / "sweep.json").read_text())
    stale["at"] = time.time() - sweep.COOLDOWN - 1
    (tmp_home / "sweep.json").write_text(json.dumps(stale))
    assert sweep.cooling() == 0


def test_corrupt_state_file_reads_as_empty(tmp_home):
    (tmp_home / "sweep.json").write_text("{not json")
    assert sweep.last() == {}
    assert sweep.cooling() == 0


def test_since_uses_the_last_sweep_on_the_same_day(tmp_home):
    sweep.record(0, "")
    clock = sweep.last()["clock"]
    assert clock in sweep.since()
    assert "last sweep" in sweep.since()


def test_since_ignores_a_sweep_from_another_day(tmp_home):
    (tmp_home / "sweep.json").write_text(json.dumps({
        "at": time.time(), "clock": "18:20", "day": "2000-01-01",
        "logged": 4, "summary": "",
    }))
    text = sweep.since()
    assert "18:20" not in text
    assert "start of the working day" in text


def test_prompt_carries_the_port_and_the_window(tmp_home):
    text = sweep.prompt(8787)
    assert "127.0.0.1:8787" in text
    assert sweep.since() in text
    # The narrowing is the whole point of the button, so it has to survive an
    # edit to the prompt.
    assert "strong evidence" in text
    assert "nothing new" in text


def test_allowlist_lets_the_sweep_reach_the_dashboard(tmp_home):
    allow = sweep.allowed()
    # curl is what earns the cats. Endpoint-specific patterns were tried and
    # every one of them missed on flag ordering, so the grant is curl itself.
    assert "Bash(curl:*)" in allow


def test_allowlist_hands_over_no_general_shell(tmp_home):
    allow = sweep.allowed()
    assert not any(a in ("Bash", "Bash(*)", "Bash(:*)") for a in allow)
    # A sweep reads and logs. Nothing in it should be editing files.
    assert "Write" not in allow
    assert "Edit" not in allow
    assert "NotebookEdit" not in allow


def test_prompt_asks_for_weak_items_rather_than_dropping_them(tmp_home):
    # An unsent draft is invisible everywhere else, so a sweep that silently
    # discards the weak bucket loses the signal the sweep exists to find.
    assert "weak:" in sweep.prompt(8787)


def test_done_writes_need_a_sync_before_they_count(tmp_home):
    """The count is a herd delta, and /api/done does not touch the herd.

    A real sweep logged seven completions and reported zero, because the cats
    are awarded by sync_day_file on the next state read rather than by the POST
    that wrote the line.
    """
    from app import cats, state

    cats.sync_day_file()
    before = len(cats.herd()["today"])

    for text in ("posted the announcement", "merged PR 14", "answered the partner"):
        state.append_done(text)

    # The failure this guards: counting here reports nothing found.
    assert len(cats.herd()["today"]) == before

    cats.sync_day_file()
    assert len(cats.herd()["today"]) - before == 3


def test_summary_keeps_the_head_now_that_it_is_only_the_answer(tmp_home):
    """The route passes the final text block, so the head is the useful part.

    An earlier version joined every text block and kept the tail, which made
    the stored summary 4000 characters of mid-sentence narration.
    """
    sweep.record(2, "x" * 5000)
    stored = sweep.last()["summary"]
    assert len(stored) == 4000
    assert stored.startswith("x")


def test_bound_port_prefers_the_real_socket(tmp_home):
    """The agent is a separate process, so it needs a port that reaches the app.

    request.url.port is the port the browser used, which is the same thing
    normally and the wrong thing behind anything that rewrites the host.
    """
    # app.main refuses to import without a config, which is the guard that
    # sends a fresh install to the setup wizard.
    (tmp_home / "config.toml").write_text(
        '[general]\ntimezone = "UTC"\nday_starts_at = 6\n'
        '[tasks]\nprovider = "localfile"\n[mail]\nprovider = "none"\n'
    )
    from app.main import _bound_port

    class Req:
        def __init__(self, scope, url_port):
            self.scope = scope
            self.url = type("U", (), {"port": url_port})()

    assert _bound_port(Req({"server": ("127.0.0.1", 8799)}, 9999)) == 8799
    assert _bound_port(Req({}, 9001)) == 9001
    assert _bound_port(Req({}, None)) == 8787


def test_trim_drops_process_narration(tmp_home):
    """The prompt asks for no narration and three runs ignored it. The
    trimmer is the guarantee the prompt is not."""
    text = ("Both sweeps are in. Now judging.\n\n"
            "Applying triage: all 22 inbox messages drop.\n\n"
            "Answered Melody on the CCM video comment.")
    out = sweep.trim_summary(text)
    assert "Both sweeps" not in out
    assert "Applying triage" not in out
    assert "Answered Melody" in out


def test_trim_caps_word_count(tmp_home):
    out = sweep.trim_summary("word " * 400, max_words=150)
    assert len(out.split()) <= 151  # 150 plus the ellipsis
    assert out.endswith("...")


def test_trim_keeps_short_replies_whole(tmp_home):
    assert sweep.trim_summary("nothing new") == "nothing new"


def test_trim_never_returns_empty(tmp_home):
    """If every line looks like narration, keep the original rather than
    storing a blank summary that hides what happened."""
    assert sweep.trim_summary("Let me check the sweeps").strip()


def test_record_stores_the_trimmed_version(tmp_home):
    sweep.record(1, "Both sweeps are in. Now judging.\n\nLogged one thing.")
    assert "Both sweeps" not in sweep.last()["summary"]


def test_usage_db_is_staged_outside_the_sandbox(tmp_home, tmp_path, monkeypatch):
    """Claude Code sandboxes ~/Library whatever the tool allowlist grants.

    Runs were spending a tool call discovering they could not open the file
    and then reporting the gap as a finding, which is how the only source
    that sees work leaving no artifact went missing for a whole morning.
    """
    src = tmp_path / "usage.db"
    src.write_bytes(b"sqlite-ish")
    dst = tmp_path / "staged.db"
    monkeypatch.setattr(sweep, "USAGE_DB", src)
    monkeypatch.setattr(sweep, "USAGE_COPY", dst)

    assert sweep.stage_usage_db() == str(dst)
    assert dst.read_bytes() == b"sqlite-ish"


def test_missing_tracker_is_not_an_error(tmp_home, tmp_path, monkeypatch):
    monkeypatch.setattr(sweep, "USAGE_DB", tmp_path / "nope.db")
    assert sweep.stage_usage_db() == ""


def test_prompt_names_the_staged_path(tmp_home, tmp_path, monkeypatch):
    src = tmp_path / "usage.db"
    src.write_bytes(b"x")
    dst = tmp_path / "staged.db"
    monkeypatch.setattr(sweep, "USAGE_DB", src)
    monkeypatch.setattr(sweep, "USAGE_COPY", dst)

    body = sweep.prompt(8787)
    assert str(dst) in body
    assert "cannot reach the original" in body


def test_prompt_says_skip_when_tracker_absent(tmp_home, tmp_path, monkeypatch):
    """Better to tell the agent to skip than let it hunt for a missing file."""
    monkeypatch.setattr(sweep, "USAGE_DB", tmp_path / "nope.db")
    body = sweep.prompt(8787)
    assert "skip it rather than hunt" in body


def test_gatherer_is_told_not_to_touch_library(tmp_home):
    p = sweep.agents()["sweep-activity"]["prompt"]
    assert "ALREADY been copied" in p
    assert "~/Library" in p


def test_activity_gatherer_covers_docs_and_ccvault(tmp_home):
    """Docs and ccvault are the only view of work done in another window.

    A morning of parallel Claude sessions went unreported because the
    gatherer never ran the docs call and nothing asked it to name the
    sessions behind the edits.
    """
    p = sweep.agents()["sweep-activity"]["prompt"]
    assert "/api/docs" in p
    assert "ccvault" in p


def test_prompt_hands_the_base_url_to_the_gatherers(tmp_home):
    assert "dashboard URL http://127.0.0.1:8787" in sweep.prompt(8787)


def test_prompt_says_notion_rows_come_named(tmp_home):
    body = sweep.prompt(8787).lower()
    assert "real names" in body

def test_window_is_bounded_at_both_ends(tmp_home):
    """A start time alone lets the gatherer pick its own end.

    The 21:06 scheduled run asked for "since 19:06", and the Slack search came
    back with messages from 21:51 and 22:06 that had not happened when the
    window opened. Its own summary said "returned stale results outside the
    window". A window needs an end.
    """
    (tmp_home / "sweep.json").write_text(json.dumps({
        "at": time.time(), "clock": "09:15", "day": state.working_day(),
        "logged": 0, "summary": "",
    }))
    lo, hi = sweep.window()
    assert lo == "09:15"
    assert hi == state.today().strftime("%H:%M")
    assert lo < hi


def test_window_end_is_the_current_clock(tmp_home):
    sweep.record(0, "")
    assert sweep.window()[1] == state.today().strftime("%H:%M")


def test_since_still_names_the_last_sweep(tmp_home):
    sweep.record(0, "")
    assert sweep.last()["clock"] in sweep.since()
    assert "last sweep" in sweep.since()


def test_prompt_states_both_ends_of_the_window(tmp_home):
    sweep.record(0, "")
    lo, hi = sweep.window()
    text = sweep.prompt(8787)
    assert lo in text
    assert hi in text


def test_prompt_demands_a_dated_slack_filter(tmp_home):
    """`on:<day>` returns the day's newest N messages, not the window's.

    Sorted newest-first and truncated by `limit`, the window's messages fall
    off the end entirely. The prompt has to require the bounded form.
    """
    text = sweep.prompt(8787)
    assert "after:" in text
    assert "before:" in text


def test_prompt_forbids_trusting_an_unbounded_result(tmp_home):
    text = sweep.prompt(8787).lower()
    assert "the filter did not apply" in text
    assert "re-run it bounded" in text
