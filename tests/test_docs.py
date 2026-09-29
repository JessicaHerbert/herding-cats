import json

from app import docs


def test_notion_ref_update_call_is_a_real_id():
    page_id, title, parent_only = docs._notion_ref({"page_id": "abc456"})
    assert page_id == "abc456"
    assert title == ""
    assert parent_only is False


def test_notion_ref_creation_call_is_parent_only():
    args = {
        "pages": [{"properties": {"title": "Weekly notes"}}],
        "parent": {"page_id": "abc123"},
    }
    page_id, title, parent_only = docs._notion_ref(args)
    assert page_id == "abc123"
    assert title == "Weekly notes"
    assert parent_only is True


def test_notion_ref_data_string_carries_the_id():
    args = {"data": json.dumps({"page_id": "abc789"})}
    assert docs._notion_ref(args)[0] == "abc789"


def test_fetch_title_parses_the_title_property(tmp_home, monkeypatch):
    class Reply:
        stdout = json.dumps({"properties": {
            "Name": {"type": "title",
                     "title": [{"plain_text": "OSP Labs"}]},
        }})

    monkeypatch.setattr(docs.subprocess, "run", lambda *a, **k: Reply())
    assert docs._fetch_title("abc") == "OSP Labs"


def test_fetch_title_failure_is_empty(tmp_home, monkeypatch):
    def boom(*args, **kwargs):
        raise docs.subprocess.TimeoutExpired(cmd="ntn", timeout=1)

    monkeypatch.setattr(docs.subprocess, "run", boom)
    assert docs._fetch_title("abc") == ""


def test_fetch_title_missing_title_property_is_empty(tmp_home, monkeypatch):
    class Reply:
        stdout = json.dumps({"properties": {
            "Status": {"type": "select", "select": None},
        }})

    monkeypatch.setattr(docs.subprocess, "run", lambda *a, **k: Reply())
    assert docs._fetch_title("abc") == ""


def test_title_cache_round_trip(tmp_home):
    docs._save_titles({"abc": "OSP Labs"})
    assert docs._load_titles().get("abc") == "OSP Labs"


def test_corrupt_title_cache_reads_as_empty(tmp_home):
    docs._titles_file().write_text("{not json")
    assert docs._load_titles() == {}
