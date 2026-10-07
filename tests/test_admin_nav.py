"""The admin page and the way into it.

Reaching the herd and its history used to mean finding the "see the herd"
link inside a card partway down the dashboard. The header link is the front
door now, so these pin that it exists, that it points somewhere real, and
that every panel it promises is actually present.
"""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
INDEX = (WEB / "index.html").read_text()
ADMIN = (WEB / "history.html").read_text()
CSS = (WEB / "app.css").read_text()
JS = (WEB / "history.js").read_text()


def test_header_carries_an_admin_link():
    assert 'id="admin"' in INDEX, "no admin entry in the header"
    assert 'href="/history.html"' in INDEX


def test_admin_link_opens_in_place():
    """Without data-open-page the click handler hands it to the system
    browser, which is signed into nothing and shows an empty dashboard."""
    link = re.search(r'<a id="admin"[^>]*>', INDEX)
    assert link and "data-open-page" in link.group(0)


def test_admin_link_is_styled_with_the_other_header_controls():
    """It sits in a flex row of 29px buttons. Left to the default link
    styling it renders as blue underlined text at the wrong height."""
    for rule in ("#log-done,#add-task,#admin{", "#admin{"):
        assert rule in CSS, f"missing style rule: {rule}"
    assert "text-decoration:none" in CSS


def test_every_promised_panel_exists():
    for tab in ("herd", "days"):
        assert f'data-tab="{tab}"' in ADMIN, f"no tab for {tab}"
        assert f'id="panel-{tab}"' in ADMIN, f"no panel for {tab}"


def test_tabs_and_panels_match_exactly():
    """A tab pointing at a panel that does not exist shows a blank page."""
    tabs = set(re.findall(r'data-tab="([a-z]+)"', ADMIN))
    panels = set(re.findall(r'id="panel-([a-z]+)"', ADMIN))
    assert tabs == panels, f"tabs {tabs} do not match panels {panels}"


def test_only_one_panel_starts_visible():
    assert ADMIN.count("data-panel hidden") == 1


def test_selected_tab_is_remembered():
    assert "localStorage" in JS and "herd-tab" in JS
