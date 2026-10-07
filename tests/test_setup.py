import tomllib

from app import paths, setup


def test_needed_when_no_config(tmp_home):
    assert setup.needed() is True


def test_not_needed_once_written(tmp_home):
    (tmp_home / "config.toml").write_text('[tasks]\nprovider = "localfile"\n')
    assert setup.needed() is False


def test_write_config_round_trips(tmp_home):
    cfg = {
        "general": {"timezone": "UTC", "day_starts_at": 5},
        "tasks": {"provider": "localfile", "path": "/tmp/t.md",
                  "token": "", "tasklist": ""},
        "mail": {"provider": "none", "address": ""},
    }
    written = setup.write_config(cfg)
    back = tomllib.loads(written.read_text())
    assert back["general"]["day_starts_at"] == 5
    assert back["tasks"]["provider"] == "localfile"
    assert back["mail"]["provider"] == "none"
    assert "token" not in back["tasks"]


def test_localfile_walkthrough(tmp_home):
    answers = iter(["UTC", "6", "n", "3", str(tmp_home / "tasks.md"), "2", "n"])
    said = []
    setup.run(input_fn=lambda _="": next(answers), output_fn=said.append)

    cfg = tomllib.loads(paths.config_file().read_text())
    assert cfg["tasks"]["provider"] == "localfile"
    assert cfg["mail"]["provider"] == "none"
    assert (tmp_home / "tasks.md").exists()
    assert any("config.toml" in s for s in said)


def test_blank_answers_take_the_defaults(tmp_home):
    answers = iter(["", "", "", "3", str(tmp_home / "t.md"), "2", "n"])
    setup.run(input_fn=lambda _="": next(answers), output_fn=lambda _: None)
    cfg = tomllib.loads(paths.config_file().read_text())
    assert cfg["general"]["day_starts_at"] == 6


def test_the_wizard_refuses_a_zone_it_cannot_load(tmp_home):
    """The detected default used to be an abbreviation like EDT. Writing it
    produced a config that printed success and then would not start."""
    answers = iter(["EDT", "America/New_York", "6", "n", "3",
                    str(tmp_home / "t.md"), "2", "n"])
    said = []
    setup.run(input_fn=lambda _="": next(answers), output_fn=said.append)

    assert any("not a zone name" in s for s in said)
    cfg = tomllib.loads(paths.config_file().read_text())
    assert cfg["general"]["timezone"] == "America/New_York"


def test_scan_offer_defaults_to_no(tmp_home):
    """A blank answer skips the scan, so scripted runs and answers like the
    ones above never trigger a machine sweep by accident."""
    answers = iter(["UTC", "6", "", "3", str(tmp_home / "t.md"), "2", "n"])
    said = []
    setup.run(input_fn=lambda _="": next(answers), output_fn=said.append)
    assert not any("What I found" in s for s in said)


def test_scan_runs_when_accepted_and_sets_the_defaults(tmp_home):
    """A real answer to 'what do you use for tasks' should already be
    selected when the menu comes up, from what the scan found. The
    recommendation shows as the default on the Choice prompt; the answers
    then take the localfile path so the check passes offline."""
    def fake_scan(output_fn):
        output_fn("(scan ran)\n")
        return {"task_default": "todoist", "mail_default": "gmail"}

    answers = iter(["UTC", "6", "y", "3", str(tmp_home / "t.md"), "2", "n"])
    said = []
    setup.run(input_fn=lambda _="": next(answers), output_fn=said.append,
              scan_fn=fake_scan)

    assert any("(scan ran)" in s for s in said)
    # The task menu defaulted to 2 (Todoist) because the scan said so.
    choice_prompts = [x for x in said if x.startswith("Choice")]
    assert choice_prompts and "[2]" in choice_prompts[0]
    cfg = tomllib.loads(paths.config_file().read_text())
    assert cfg["tasks"]["provider"] == "localfile"
    assert cfg["mail"]["provider"] == "none"
