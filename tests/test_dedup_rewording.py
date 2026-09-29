"""The same work described two different ways must earn one cat.

A day file gets written in batches, and the same piece of work often gets
described once in the evening sweep and again later in different words. On
2026-09-14 "Answered the Allowed Amounts question for the customer" and
"Sent the Allowed Amounts answer to the customer and the internal team"
both earned a cat, because the old key took the first five words and those
two openings share none.
"""

from app import cats


def test_restated_task_matches():
    """The same task logged twice, reworded lightly, earns one cat.

    This is the common shape: a task title and a day-file line describing
    the same thing with a different tense or a trailing clause.
    """
    assert cats._same_work(
        "Answer Payton on whether Joel Brewer will take a reference call",
        "Answered Payton on whether Joel Brewer will take a reference call",
    )
    assert cats._same_work(
        "Caught PHI sent over unsecured email on the Amae lab-order thread, "
        "removed the attachment",
        "Flagged unsecured PHI in the Amae lab order email thread, removed "
        "the attachment",
    )


def test_heavy_reword_is_left_to_the_sweep():
    """A full reword is NOT merged here, on purpose.

    The 2026-09-14 Allowed Amounts pair scores 0.500, identical to
    "Installed Studio on candidate-sandbox" vs "Installed a batch of plugins
    on candidate-sandbox", which is two real installs. No threshold splits
    them, so this stays a judgment call for the sweep rather than a guess
    that silently eats an earned cat.
    """
    a = ("Answered the Allowed Amounts question for the customer, working it "
         "with Bex and replying to the customer directly")
    b = ("Sent the Allowed Amounts answer to the customer and the internal "
         "team, after working the queries with Bex")
    assert not cats._same_work(a, b)

    c = "Installed Studio on candidate-sandbox"
    d = "Installed a batch of plugins on candidate-sandbox"
    assert not cats._same_work(c, d)


def test_repeat_marker_keeps_them_separate():
    assert not cats._same_work(
        "Replied to Thomas Tabi at Grain on the Fathom migration",
        "Replied again to Thomas Tabi at Grain on the Fathom migration",
    )


def test_block_suffix_still_matches_bare_title():
    assert cats._key("Answer SAF") == cats._key("Answer SAF (08:30 block)")
    assert cats._same_work("Answer SAF", "Answer SAF (08:30 block)")


def test_distinct_work_does_not_collide():
    a = "Drafted the CCM social 3 post and shared it with Melody"
    b = "Pulled the marketing activity roundup for August and September"
    assert not cats._same_work(a, b)


def test_same_topic_different_work_does_not_collide():
    """Sharing a subject is not the same as being the same task."""
    a = "Opened the Surescripts incident channel and sent the broadcast"
    b = "Closed out the Surescripts outage after confirming with Beau"
    assert not cats._same_work(a, b)


def test_real_day_stays_distinct():
    """Every pair from a real day file must stay separate.

    Guards the overlap threshold against being loosened until it starts
    eating cats she actually earned.
    """
    day = [
        "Closed out the Surescripts gateway outage after confirming with Beau "
        "that Monday's reports were a separate issue, having run comms across "
        "both days",
        "Covered support and implementation escalations for the evening, "
        "posted the heads-up in both team channels and arranged backup",
        "Drafted the initiatives work: what-do-we-want, the specialty prospect "
        "experience, the trial journey plan and the appendix",
        "Pulled the marketing activity roundup covering August 12 to "
        "September 14",
        "Ran the Monday meeting block: Adam and Melody monthly sync, "
        "Onboarding Status Review, Contracts review, and Pipeline Review",
        "Finished the CCM social 3 post refocused on customizing in Studio "
        "and shared it with Melody for format feedback",
        "Unblocked the WLM page by handing Investigator the renamed marketing "
        "summary and directing it to fix the P0 data gap and open the PR",
    ]
    for i, a in enumerate(day):
        for b in day[i + 1:]:
            assert not cats._same_work(a, b), f"merged:\n  {a}\n  {b}"


def test_short_titles_still_work():
    assert cats._same_work("Prep WLM", "Prep WLM")
    assert not cats._same_work("Prep WLM", "Process Leads")


def test_empty_title_is_stable():
    assert cats._key("") == cats._key(None)
    assert not cats._same_work("", "Prep WLM")


def test_is_duplicate_checks_against_a_list():
    existing = ["Prep WLM", "Pulled the marketing activity roundup"]
    assert cats._is_duplicate("Prep WLM (14:00 block)", existing)
    assert not cats._is_duplicate("Process Leads and Contacts", existing)
