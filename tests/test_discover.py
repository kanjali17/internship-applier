from discover import score

def x(title, company="Acme", loc="San Francisco, CA", term="Summer 2027"):
    return {"title": title, "company": company, "locations": [loc], "term": term}

def test_tracks_and_ranking():
    t1, s1, _ = score(x("AI Engineer Intern"), 2)
    t2, s2, _ = score(x("Software Engineer Intern"), 2)
    assert t1 == "ai_eng" and t2 == "swe" and s1 > s2

def test_pm_is_sticky():
    t, _, _ = score(x("AI Product Manager Intern"), 2)
    assert t == "pm"

def test_excluded_titles_and_age():
    assert score(x("PhD Research Intern, ML"), 2)[0] is None
    assert score(x("Software Engineer Intern"), 90)[0] is None

def test_fresher_and_tier_score_higher():
    _, fresh, _ = score(x("Software Engineer Intern"), 1)
    _, old, _ = score(x("Software Engineer Intern"), 20)
    _, dream, _ = score(x("Software Engineer Intern", company="Anthropic"), 20)
    assert fresh > old and dream > old

def test_offcycle_only_top_tier():
    assert score(x("Software Engineer Co-op", term="Spring 2027"), 2)[0] is None
    assert score(x("Software Engineer Co-op", company="OpenAI", term="Spring 2027"), 2)[0] == "swe"
