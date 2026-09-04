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


def test_a_scratch_install_is_not_offered_the_real_day_files(tmp_home, tmp_path):
    """OLD_DAILY is one machine's absolute path. A clone pointed at a
    temporary HERD_HOME used to be offered those day files, and run()
    deletes originals after copying."""
    real_daily = tmp_path / "someones-real-daily"
    real_daily.mkdir()
    (real_daily / "2026-09-01.md").write_text("# a real day")
    monkey = migrate.OLD_DAILY
    try:
        migrate.OLD_DAILY = real_daily
        found = migrate.find_old(repo_root=tmp_path)
        assert "daily" not in found
        assert (real_daily / "2026-09-01.md").exists()
    finally:
        migrate.OLD_DAILY = monkey


def test_the_owning_install_is_still_offered_them(tmp_path, monkeypatch):
    """At the default HERD_HOME the offer must still happen, or the one
    person with data to migrate never gets it moved."""
    from app import paths as paths_mod

    home = tmp_path / "default-home"
    monkeypatch.setattr(paths_mod, "DEFAULT_HOME", str(home))
    monkeypatch.setenv("HERD_HOME", str(home))
    real_daily = tmp_path / "owning-daily"
    real_daily.mkdir()
    (real_daily / "2026-09-01.md").write_text("# a real day")
    monkey = migrate.OLD_DAILY
    try:
        migrate.OLD_DAILY = real_daily
        found = migrate.find_old(repo_root=tmp_path)
        assert "daily" in found
    finally:
        migrate.OLD_DAILY = monkey


def test_a_scratch_install_is_not_offered_the_repo_root_herd(tmp_home, tmp_path):
    """run() unlinks the original after copying, so a throwaway HERD_HOME must
    not be shown a herd that belongs to a real install. tmp_home is not the
    default location, so find_old should decline to offer either file."""
    checkout = tmp_path / "someones-checkout"
    checkout.mkdir()
    (checkout / "herd.json").write_text('{"days": {}, "total": 109}')
    (checkout / "picks.json").write_text("{}")

    found = migrate.find_old(old_daily=tmp_path / "no-daily")

    assert "herd" not in found
    assert "picks" not in found
    assert (checkout / "herd.json").exists()


def test_an_explicit_root_is_still_honored(tmp_home, tmp_path):
    """Passing repo_root is a deliberate act, so it overrides the guard.
    The tests above rely on this to drive migration at all."""
    checkout = tmp_path / "explicit"
    checkout.mkdir()
    (checkout / "herd.json").write_text('{"days": {}, "total": 1}')

    found = migrate.find_old(repo_root=checkout, old_daily=tmp_path / "no-daily")

    assert "herd" in found
