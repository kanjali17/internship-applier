import tempfile, pathlib
import tracker

def _tmp():
    d = pathlib.Path(tempfile.mkdtemp()) / "tracker.xlsx"
    tracker.path = lambda: d
    return d

def test_different_link_is_a_new_row():
    _tmp()
    r1, _ = tracker.upsert("Excluded", "Acme", "APM Intern (Hybrid)", link="https://x.io/jobs/1")
    r2, updated = tracker.upsert("Needs answer", "Acme", "APM Summer Internship (Hybrid)", link="https://x.io/jobs/2")
    assert r2 != r1 and not updated

def test_same_link_updates_row():
    _tmp()
    r1, _ = tracker.upsert("Needs answer", "Acme", "Data Intern", link="https://x.io/jobs/3")
    r2, updated = tracker.upsert("Submitted", "Acme", "Data Intern", link="https://x.io/jobs/3?gh_src=abc")
    assert r2 == r1 and updated

def test_never_downgrades_submitted():
    _tmp()
    tracker.upsert("Submitted", "Acme", "AI Intern", link="https://x.io/jobs/4")
    try:
        tracker.upsert("Excluded", "Acme", "AI Intern", link="https://x.io/jobs/4")
        assert False, "should refuse"
    except SystemExit as e:
        assert "already 'Submitted'" in str(e)
