import pytest


@pytest.fixture
def tmp_home(tmp_path, monkeypatch):
    """An isolated HERD_HOME, so tests never touch the real herd."""
    home = tmp_path / "herd-home"
    home.mkdir()
    monkeypatch.setenv("HERD_HOME", str(home))
    return home
