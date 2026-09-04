import json

from app import migrate, paths


def test_finds_nothing_when_there_is_nothing(tmp_home, tmp_path):
    assert migrate.find_old(repo_root=tmp_path, old_daily=tmp_path / "nope") == {}


def test_finds_old_data(tmp_home, tmp_path):
    (tmp_path / "herd.json").write_text('{"days": {}, "total": 0}')
    old_daily = tmp_path / "daily"
    old_daily.mkdir()
    (old_daily / "2026-09-01.md").write_text("# day")
    found = migrate.find_old(repo_root=tmp_path, old_daily=old_daily)
    assert "herd" in found and "daily" in found


def test_run_moves_and_verifies(tmp_home, tmp_path):
    herd = {"days": {"2026-09-01": [{"for": "a"}, {"for": "b"}]}, "total": 2}
    (tmp_path / "herd.json").write_text(json.dumps(herd))
    old_daily = tmp_path / "daily"
    old_daily.mkdir()
    (old_daily / "2026-09-01.md").write_text("# day one")
    (old_daily / "2026-09-02.md").write_text("# day two")

    found = migrate.find_old(repo_root=tmp_path, old_daily=old_daily)
    result = migrate.run(found)

    assert result["cats"] == 2
    assert result["daily"] == 2
    moved = json.loads(paths.herd_file().read_text())
    assert moved["total"] == 2
    assert (paths.daily_dir() / "2026-09-02.md").read_text() == "# day two"
    assert not (tmp_path / "herd.json").exists()


def test_original_survives_a_bad_copy(tmp_home, tmp_path):
    (tmp_path / "herd.json").write_text("{ not json")
    found = migrate.find_old(repo_root=tmp_path, old_daily=tmp_path / "nope")
    result = migrate.run(found)
    assert result["cats"] == 0
    assert (tmp_path / "herd.json").exists()


def test_never_overwrites_existing(tmp_home, tmp_path):
    paths.ensure()
    paths.herd_file().write_text('{"days": {}, "total": 99}')
    (tmp_path / "herd.json").write_text('{"days": {}, "total": 1}')
    found = migrate.find_old(repo_root=tmp_path, old_daily=tmp_path / "nope")
    migrate.run(found)
    assert json.loads(paths.herd_file().read_text())["total"] == 99


def test_a_valid_picks_file_is_reported_as_moved(tmp_home, tmp_path):
    (tmp_path / "picks.json").write_text('{"2026-09-04": ["abc"]}')
    found = migrate.find_old(repo_root=tmp_path, old_daily=tmp_path / "nope")
    result = migrate.run(found)
    assert result["picks"] == 1
    assert json.loads(paths.picks_file().read_text()) == {"2026-09-04": ["abc"]}
    assert not (tmp_path / "picks.json").exists()


def test_a_failed_writeback_is_not_reported_as_moved(tmp_home, tmp_path, monkeypatch):
    """The copy is written before it is verified, so a write that lands
    corrupted still leaves a file at the destination. Success has to come
    from the verification, not from the file merely existing."""
    (tmp_path / "picks.json").write_text('{"2026-09-04": ["abc"]}')
    destination = paths.picks_file()

    real_write = migrate.Path.write_text

    def corrupting_write(self, data, *a, **kw):
        if self == destination:
            return real_write(self, '{"tampered": true}', *a, **kw)
        return real_write(self, data, *a, **kw)

    monkeypatch.setattr(migrate.Path, "write_text", corrupting_write)
    found = migrate.find_old(repo_root=tmp_path, old_daily=tmp_path / "nope")
    result = migrate.run(found)

    assert result["picks"] == 0
    assert (tmp_path / "picks.json").exists()
