"""The hourly launchd sweep depends on things nothing else asserts.

The schedule fires scripts/hourly-sweep.sh every hour 08:05-18:05 Mon-Fri.
That script holds no scheduling logic of its own on purpose: it asks the app
whether a run is warranted and posts. These tests pin the app-side behavior
it relies on, plus the shape of the plist and the script itself, so a change
to either surfaces here rather than as a silent hour with no cats.
"""

import plistlib
import subprocess
from pathlib import Path

from app import sweep

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "hourly-sweep.sh"
PLIST = REPO / "scripts" / "com.canvas.herding-cats-sweep.plist"


def test_cooldown_is_shorter_than_the_hourly_interval(tmp_home):
    """An hourly job must never be refused by the cooldown it did not cause.

    At 3600s apart, a 900s cooldown has long expired. If COOLDOWN is ever
    raised past an hour, every scheduled run starts returning 429 and the
    pile silently stops filling.
    """
    assert sweep.COOLDOWN < 3600


def test_window_after_an_hourly_run_is_the_gap_not_the_whole_day(tmp_home):
    """Consecutive runs must not re-sweep the same hours.

    Without this the 5pm run would cover the whole day again, re-finding
    everything already logged and leaning on dedup to sort it out.
    """
    sweep.record(2, "logged two")
    assert "last sweep" in sweep.since()


def test_first_run_of_the_day_covers_from_the_day_start(tmp_home):
    """The 08:05 run has no earlier sweep to anchor to.

    It must reach back to the start of the working day rather than the last
    24 hours, or Monday morning re-reports all of Sunday evening.
    """
    assert "start of the working day" in sweep.since()


def test_script_exists_and_is_executable():
    assert SCRIPT.exists(), "hourly-sweep.sh is missing"
    assert SCRIPT.stat().st_mode & 0o111, "hourly-sweep.sh is not executable"


def test_script_is_valid_shell():
    r = subprocess.run(["zsh", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_script_skips_rather_than_starting_a_server():
    """A closed dashboard window is the normal overnight state.

    The script must exit quietly, never launch uvicorn behind her back.
    """
    body = SCRIPT.read_text()
    # Asserting on "lsof -ti:" passed against a COMMENT explaining why lsof
    # was removed, so it would have stayed green with the check deleted.
    # Assert the behavior instead: it asks the server, and it never starts one.
    assert "/api/sweep" in body, "no check that the dashboard is answering"
    assert "exit 0" in body, "no quiet exit when the dashboard is down"
    assert "uvicorn" not in body, "the scheduled job must not start a server"


def test_script_targets_the_real_port():
    assert "PORT=8787" in SCRIPT.read_text()


def test_plist_is_valid_and_covers_weekday_working_hours():
    """Every two hours, 08:05-18:05, Mon-Fri.

    Halved from hourly because ~$0.75 of a $0.79 run is fixed startup
    overhead that cannot be dropped without losing the Slack plugin's
    OAuth, and Slack supplied two of the three cats the schedule caught on
    its first day. Cutting the run count was the only lever that did not
    cost a source.
    """
    data = plistlib.loads(PLIST.read_bytes())
    slots = data["StartCalendarInterval"]

    hours = sorted({s["Hour"] for s in slots})
    days = sorted({s["Weekday"] for s in slots})

    assert hours == [8, 10, 12, 14, 16, 18], f"expected even hours 08-18, got {hours}"
    assert days == [1, 2, 3, 4, 5], f"expected Mon-Fri, got {days}"
    assert len(slots) == 30, f"expected 6 hours x 5 days, got {len(slots)}"


def test_schedule_gap_is_within_the_day_file_window():
    """A two-hour gap still has to beat reconstructing at 8pm.

    The failure this schedule exists to fix was a whole day logged in two
    evening dumps. Anything up to a few hours is still a live record; if
    the gap ever grows past that, the schedule stops solving the problem.
    """
    data = plistlib.loads(PLIST.read_bytes())
    hours = sorted({s["Hour"] for s in data["StartCalendarInterval"]})
    gaps = [b - a for a, b in zip(hours, hours[1:])]
    assert max(gaps) <= 2, f"gap of {max(gaps)}h is too long to call this live"


def test_plist_points_at_the_script_that_exists():
    data = plistlib.loads(PLIST.read_bytes())
    target = Path(data["ProgramArguments"][-1])
    assert target.exists(), f"plist points at a missing script: {target}"
    assert target.name == SCRIPT.name


def test_plist_puts_claude_on_path():
    """launchd does not source a shell profile, so ~/.local/bin is absent.

    Without it the run dies on "claude: command not found" and the only
    trace is a stderr log nobody opens.
    """
    data = plistlib.loads(PLIST.read_bytes())
    assert ".local/bin" in data["EnvironmentVariables"]["PATH"]


def test_gatherers_run_on_a_cheap_model():
    """Gathering is delegated so the bulk of the tokens are not on the
    default model. If a gatherer loses its pin it silently inherits the
    parent's model and the scheduled runs get expensive with no error."""
    for name, spec in sweep.agents().items():
        assert spec.get("model") == "haiku", f"{name} is not pinned to haiku"


def test_parent_can_actually_reach_the_gatherers():
    """--agents definitions are inert without Task in --allowedTools.

    Verified by running the CLI: without it the parent never delegates and
    everything falls back to the default model, which is the exact cost
    shape the split exists to avoid.
    """
    assert "Task" in sweep.allowed()


def test_gatherers_are_told_not_to_judge():
    """A subagent that decides what counts as done is the failure mode.

    It has less context, cannot ask, and its conclusion reads as confidently
    as the parent's own.
    """
    for name, spec in sweep.agents().items():
        assert "never decide" in spec["prompt"].lower(), f"{name} may judge"


def test_gatherers_carry_the_query_traps():
    """The two query mistakes that have each produced a wrong answer."""
    msgs = sweep.agents()["sweep-messages"]["prompt"]
    assert "in:sent" in msgs and "from:me" in msgs

    act = sweep.agents()["sweep-activity"]["prompt"]
    assert "epoch" in act.lower()


def test_prompt_tells_the_parent_to_judge_and_delegate():
    body = sweep.PROMPT
    assert "sweep-messages" in body and "sweep-activity" in body
    assert "JUDGING yourself" in body


def test_prompt_handles_running_unattended():
    """On the schedule nobody is watching, so it must never ask."""
    body = sweep.PROMPT
    assert "unattended" in body.lower()
    assert "Never ask a question" in body


def test_judging_model_is_pinned():
    """Unpinned, a scheduled job's cost depends on whatever the CLI happens
    to default to, which has nothing to do with this app."""
    assert sweep.MODEL in {"haiku", "sonnet", "opus"}


def test_judging_model_is_not_the_most_expensive():
    """Measured: opus was $1.35 of a $1.60 sweep, on 20 input tokens and
    5,795 output. The parent WRITING is the spend, so the model doing the
    writing is the lever."""
    assert sweep.MODEL != "opus"


def test_reply_length_is_capped_by_number_not_adjective():
    """"one short line" was already in the prompt when a run produced 5,795
    output tokens. An adjective is not a limit."""
    body = sweep.PROMPT
    assert "150 words" in body
    assert "25 words" in body
    assert "at most 5 weak items" in body.lower()


def test_prompt_bans_process_narration():
    """The first capped run still opened with "Both sweeps are in. Now
    judging." which is the run describing itself."""
    body = sweep.PROMPT
    assert "Both sweeps are in" in body
    assert "own repo" in body


def test_activity_gatherer_can_actually_read_the_usage_db():
    """The agent needs sqlite3 to query and date to convert the epoch.

    It does NOT need cp: granting it did not help, because Claude Code
    sandboxes ~/Library whatever the allowlist says. The app stages a copy
    instead (see sweep.stage_usage_db). Before that, the gatherer reported
    "permission denied, not queried" while the run still looked successful,
    so the only source that sees work leaving no artifact dropped out.
    """
    granted = sweep.allowed()
    for need in ("Bash(sqlite3:*)", "Bash(date:*)"):
        assert need in granted, f"{need} missing; usage DB cannot be read"
    assert hasattr(sweep, "stage_usage_db"), "nothing stages the database"


def test_script_does_not_depend_on_tools_outside_the_plist_path():
    """The liveness check used `lsof`, which lives in /usr/sbin.

    That directory was not on the PATH the plist provides, so every
    scheduled run exited 127 (command not found), the script read that as
    "server down", and skipped. Ten silent no-ops, an empty log, and
    `runs = 0` in launchctl, with nothing anywhere saying why.
    """
    code = "\n".join(
        line for line in SCRIPT.read_text().splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "lsof" not in code, "lsof is not on the launchd PATH; ask the server instead"


def test_liveness_check_asks_the_server():
    """A reply proves the server is up. Inspecting the port only proves
    something about the port, and only if the tool doing it can run."""
    body = SCRIPT.read_text()
    assert "/api/sweep" in body
    assert "not answering" in body


def test_plist_path_covers_sbin():
    """Belt and braces for anything else reaching for a /usr/sbin tool."""
    data = plistlib.loads(PLIST.read_bytes())
    path = data["EnvironmentVariables"]["PATH"]
    assert "/usr/sbin" in path


def test_skill_is_not_loaded_per_run():
    """Loading SKILL.md cost ~6,400 tokens every run to use two of its
    steps. Those steps are inlined in the prompt instead."""
    assert "Skill" not in sweep.allowed()
    assert "Run the rosie:herding-cats skill" not in sweep.PROMPT


def test_prompt_is_smaller_than_the_skill_it_replaced():
    """The inlined version has to stay cheaper than what it replaced, or
    the saving quietly erodes as rules get added back."""
    assert len(sweep.PROMPT) < 12_000, "prompt is growing back toward SKILL.md"


def test_no_tools_that_only_produce_output():
    """TodoWrite is a scratchpad nobody reads here. ScheduleWakeup was
    reached for four times in one run to build a loop the parent then
    abandoned. Both are pure output tokens on an unattended run."""
    granted = sweep.allowed()
    for banned in ("TodoWrite", "ScheduleWakeup"):
        assert banned not in granted


def test_narration_between_tool_calls_is_banned():
    """One run wrote nine commentary blocks before its answer. Only the
    final block reaches the dashboard, so the rest is paid-for and unread."""
    assert "Say NOTHING between tool calls" in sweep.PROMPT


def test_gatherers_are_told_to_be_terse():
    """Their replies are read by the parent, which pays per word. The
    measured runs had them writing 3,300-8,700 output tokens each."""
    for name, spec in sweep.agents().items():
        assert "Be terse" in spec["prompt"], f"{name} has no length limit"
        assert "pays for every word" in spec["prompt"]


def test_inlined_rules_stay_in_sync_with_the_skill():
    """The sweep no longer loads SKILL.md, so the evidence rules live in two
    places. This does not check they MATCH, which no test can, but it does
    check the prompt still carries each rule the skill would have supplied.
    A rule deleted from the prompt without being noticed is the failure this
    catches; a rule that drifts in wording is the one it cannot.
    """
    body = sweep.PROMPT
    for rule in (
        "strong evidence",      # what earns a cat
        "weak",                 # what gets surfaced but not logged
        "Never ask a question", # unattended behavior
        "Date every artifact",  # the window check
        "own repo",             # ignore this app's own edits
    ):
        assert rule in body, f"inlined prompt lost the {rule!r} rule"


def test_prompt_admits_the_duplication():
    """Whoever edits the skill next needs to know this copy exists."""
    assert "live here AND in the skill" in sweep.PROMPT
