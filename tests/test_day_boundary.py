from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app import config, state


@pytest.fixture
def utc_config(tmp_home):
    (tmp_home / "config.toml").write_text(
        '[general]\ntimezone = "UTC"\nday_starts_at = 6\n'
        '[tasks]\nprovider = "localfile"\npath = "/tmp/t.md"\n'
        '[mail]\nprovider = "none"\n'
    )
    config.reload()


def test_before_the_boundary_is_yesterday(utc_config, monkeypatch):
    fixed = datetime(2026, 9, 4, 1, 5, tzinfo=ZoneInfo("UTC"))
    monkeypatch.setattr(state, "today", lambda: fixed)
    assert state.working_day() == "2026-09-03"


def test_after_the_boundary_is_today(utc_config, monkeypatch):
    fixed = datetime(2026, 9, 4, 6, 1, tzinfo=ZoneInfo("UTC"))
    monkeypatch.setattr(state, "today", lambda: fixed)
    assert state.working_day() == "2026-09-04"


def test_a_custom_boundary_is_honored(tmp_home, monkeypatch):
    (tmp_home / "config.toml").write_text(
        '[general]\ntimezone = "UTC"\nday_starts_at = 4\n'
        '[tasks]\nprovider = "localfile"\npath = "/tmp/t.md"\n'
        '[mail]\nprovider = "none"\n'
    )
    config.reload()
    fixed = datetime(2026, 9, 4, 5, 0, tzinfo=ZoneInfo("UTC"))
    monkeypatch.setattr(state, "today", lambda: fixed)
    assert state.working_day() == "2026-09-04"


def test_timezone_comes_from_config(utc_config):
    assert str(state.tz()) == "UTC"
