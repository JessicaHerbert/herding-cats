import pytest

from app import config, providers


def test_localfile_resolves(tmp_home, monkeypatch):
    f = tmp_home / "tasks.md"
    f.write_text("- [ ] hi\n")
    (tmp_home / "config.toml").write_text(
        f'[tasks]\nprovider = "localfile"\npath = "{f}"\n'
        '[mail]\nprovider = "none"\n'
    )
    config.reload()
    providers.reset()
    assert providers.tasks().name == "localfile"


def test_todoist_resolves(tmp_home):
    (tmp_home / "config.toml").write_text(
        '[tasks]\nprovider = "todoist"\ntoken = "abc"\n'
        '[mail]\nprovider = "none"\n'
    )
    config.reload()
    providers.reset()
    assert providers.tasks().name == "todoist"


def test_mail_none_returns_none(tmp_home):
    (tmp_home / "config.toml").write_text(
        '[tasks]\nprovider = "todoist"\ntoken = "abc"\n'
        '[mail]\nprovider = "none"\n'
    )
    config.reload()
    providers.reset()
    assert providers.mail() is None


def test_calendar_is_none_when_tasks_are_not_google(tmp_home):
    (tmp_home / "config.toml").write_text(
        '[tasks]\nprovider = "todoist"\ntoken = "abc"\n'
        '[mail]\nprovider = "none"\n'
    )
    config.reload()
    providers.reset()
    assert providers.calendar_or_none() is None


def test_the_provider_is_cached(tmp_home):
    (tmp_home / "config.toml").write_text(
        '[tasks]\nprovider = "todoist"\ntoken = "abc"\n'
        '[mail]\nprovider = "none"\n'
    )
    config.reload()
    providers.reset()
    assert providers.tasks() is providers.tasks()
