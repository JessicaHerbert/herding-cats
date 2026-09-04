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
    answers = iter(["UTC", "6", "3", str(tmp_home / "tasks.md"), "2", "n"])
    said = []
    setup.run(input_fn=lambda _="": next(answers), output_fn=said.append)

    cfg = tomllib.loads(paths.config_file().read_text())
    assert cfg["tasks"]["provider"] == "localfile"
    assert cfg["mail"]["provider"] == "none"
    assert (tmp_home / "tasks.md").exists()
    assert any("config.toml" in s for s in said)


def test_blank_answers_take_the_defaults(tmp_home):
    answers = iter(["", "", "3", str(tmp_home / "t.md"), "2", "n"])
    setup.run(input_fn=lambda _="": next(answers), output_fn=lambda _: None)
    cfg = tomllib.loads(paths.config_file().read_text())
    assert cfg["general"]["day_starts_at"] == 6
