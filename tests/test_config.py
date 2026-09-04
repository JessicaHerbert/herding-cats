import pytest

from app import config


def test_defaults_when_no_file(tmp_home, monkeypatch):
    monkeypatch.delenv("HERD_TASKLIST", raising=False)
    monkeypatch.delenv("HERD_EMAIL", raising=False)
    cfg = config.reload()
    assert cfg["general"]["day_starts_at"] == 6
    assert cfg["general"]["timezone"]
    assert cfg["tasks"]["provider"] == "google"
    assert cfg["mail"]["provider"] == "gmail"


def test_reads_the_file(tmp_home):
    (tmp_home / "config.toml").write_text(
        '[general]\ntimezone = "UTC"\nday_starts_at = 4\n'
        '[tasks]\nprovider = "localfile"\npath = "/tmp/t.md"\n'
        '[mail]\nprovider = "none"\n'
    )
    cfg = config.reload()
    assert cfg["general"]["timezone"] == "UTC"
    assert cfg["general"]["day_starts_at"] == 4
    assert cfg["tasks"]["provider"] == "localfile"
    assert cfg["mail"]["provider"] == "none"


def test_env_overrides_file(tmp_home, monkeypatch):
    (tmp_home / "config.toml").write_text(
        '[tasks]\nprovider = "google"\ntasklist = "from-file"\n'
    )
    monkeypatch.setenv("HERD_TASKLIST", "from-env")
    monkeypatch.setenv("HERD_EMAIL", "me@example.com")
    cfg = config.reload()
    assert cfg["tasks"]["tasklist"] == "from-env"
    assert cfg["mail"]["address"] == "me@example.com"


def test_bad_toml_is_a_clear_error(tmp_home):
    (tmp_home / "config.toml").write_text("this is not = = toml")
    with pytest.raises(config.ConfigError) as e:
        config.reload()
    assert "config.toml" in str(e.value)


def test_unknown_provider_is_rejected(tmp_home):
    (tmp_home / "config.toml").write_text('[tasks]\nprovider = "nope"\n')
    with pytest.raises(config.ConfigError) as e:
        config.reload()
    assert "nope" in str(e.value)


def test_exists_reflects_the_file(tmp_home):
    assert config.exists() is False
    (tmp_home / "config.toml").write_text('[tasks]\nprovider = "localfile"\n')
    assert config.exists() is True
