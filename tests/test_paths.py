from pathlib import Path

from app import paths


def test_home_defaults_to_dot_herding_cats(monkeypatch):
    monkeypatch.delenv("HERD_HOME", raising=False)
    assert paths.home() == Path.home() / ".herding-cats"


def test_home_respects_env(tmp_home):
    assert paths.home() == tmp_home


def test_everything_hangs_off_home(tmp_home):
    assert paths.config_file() == tmp_home / "config.toml"
    assert paths.herd_file() == tmp_home / "herd.json"
    assert paths.picks_file() == tmp_home / "picks.json"
    assert paths.daily_dir() == tmp_home / "daily"


def test_ensure_creates_the_tree(tmp_path, monkeypatch):
    target = tmp_path / "fresh"
    monkeypatch.setenv("HERD_HOME", str(target))
    paths.ensure()
    assert target.is_dir()
    assert (target / "daily").is_dir()


def test_tilde_in_env_is_expanded(monkeypatch):
    monkeypatch.setenv("HERD_HOME", "~/somewhere-else")
    assert paths.home() == Path.home() / "somewhere-else"
