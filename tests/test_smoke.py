def test_app_imports():
    from app import cats, rollover, state
    assert cats and rollover and state


def test_tmp_home_is_isolated(tmp_home):
    import os
    assert os.environ["HERD_HOME"] == str(tmp_home)
    assert tmp_home.is_dir()
