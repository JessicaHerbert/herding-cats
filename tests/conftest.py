import os

import pytest


@pytest.fixture
def tmp_home(tmp_path, monkeypatch):
    """An isolated HERD_HOME, so tests never touch the real herd."""
    home = tmp_path / "herd-home"
    home.mkdir()
    monkeypatch.setenv("HERD_HOME", str(home))
    return home


@pytest.fixture(autouse=True)
def never_the_real_herd(tmp_path, monkeypatch):
    """Point HERD_HOME at scratch for EVERY test, named fixture or not.

    A test that forgot to request tmp_home used to fall through to the real
    data. One did, wrote a cat into the production herd, and undoing it threw
    away a rose quartz roll. Autouse means forgetting is no longer possible.
    """
    fallback = tmp_path / "autouse-herd-home"
    fallback.mkdir(exist_ok=True)
    monkeypatch.setenv("HERD_HOME", str(fallback))
