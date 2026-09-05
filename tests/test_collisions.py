from app.providers.google_tasks import _collisions


def ev(summary, start, end, type_="default"):
    return {"summary": summary, "start": start, "end": end, "type": type_}


OVERLAP = [
    ev("Alexia 1:1", "2026-09-04T13:00:00-04:00", "2026-09-04T13:30:00-04:00"),
    ev("Ceci 1:1", "2026-09-04T13:15:00-04:00", "2026-09-04T13:45:00-04:00"),
]


def test_overlap_is_reported_when_still_ahead():
    found = _collisions(OVERLAP, "2026-09-04T09:00:00-04:00")
    assert len(found) == 1
    assert found[0]["at"] == "13:15"


def test_overlap_still_reported_while_one_side_is_running():
    found = _collisions(OVERLAP, "2026-09-04T13:20:00-04:00")
    assert len(found) == 1


def test_overlap_drops_once_both_sides_have_ended():
    assert _collisions(OVERLAP, "2026-09-04T14:00:00-04:00") == []


def test_overlap_drops_at_the_exact_end_of_the_later_event():
    assert _collisions(OVERLAP, "2026-09-04T13:45:00-04:00") == []


def test_no_now_reports_everything():
    """Without a clock the function cannot age anything out, so it must not try."""
    assert len(_collisions(OVERLAP)) == 1


def test_non_overlapping_events_never_collide():
    back_to_back = [
        ev("Standup", "2026-09-04T09:00:00-04:00", "2026-09-04T09:30:00-04:00"),
        ev("Review", "2026-09-04T09:30:00-04:00", "2026-09-04T10:00:00-04:00"),
    ]
    assert _collisions(back_to_back, "2026-09-04T08:00:00-04:00") == []


def test_long_self_booked_hold_is_not_a_collision():
    with_hold = [
        ev("Focus block", "2026-09-04T09:00:00-04:00", "2026-09-04T17:00:00-04:00"),
        ev("Support Team", "2026-09-04T14:00:00-04:00", "2026-09-04T15:00:00-04:00"),
    ]
    assert _collisions(with_hold, "2026-09-04T08:00:00-04:00") == []
