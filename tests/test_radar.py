import json, pathlib, tempfile, xml.etree.ElementTree as ET

from radar import atom_feed, build, classify, clean_url, load_simplify, region, stats

NOW = 1_800_000_000
DAY = 86400


def listing(title, company="Acme", terms=("Summer 2027",), locs=("San Francisco, CA",), days_ago=1,
            active=True, visible=True, category="Software", url="https://boards.greenhouse.io/acme/jobs/1?utm_source=Simplify"):
    return {"id": f"{company}-{title}-{days_ago}", "company_name": company, "title": title, "terms": list(terms),
            "locations": list(locs), "date_posted": NOW - days_ago * DAY, "active": active, "is_visible": visible,
            "category": category, "url": url, "sponsorship": "Other", "degrees": ["Bachelor's"]}


def write(rows):
    d = pathlib.Path(tempfile.mkdtemp())
    p = d / "listings.json"
    p.write_text(json.dumps(rows))
    return p


def test_classify_prefers_title_words():
    assert classify("Machine Learning Engineer Intern", "Software") == "ai"
    assert classify("Software Engineer Intern - ML Platform", "Software") == "ai"
    assert classify("Associate Product Manager Intern") == "pm"
    assert classify("Quantitative Trader Intern") == "quant"
    assert classify("Data Analyst Intern") == "data"
    assert classify("Firmware Engineer Intern", "Software") == "hardware"
    assert classify("Backend Engineer Intern") == "swe"
    assert classify("Pharmacy Aggregation Intern", "AI/ML/Data") == "other"
    assert classify("Operations Intern", "Product") == "pm"  # falls back to the source category


def test_region_tags():
    assert region(["San Francisco, CA"]) == ["us"]
    assert region(["NYC"]) == ["us"]
    assert region(["Toronto, ON, Canada"]) == ["intl"]
    assert region(["London, UK", "Remote in USA"]) == ["intl", "remote", "us"]
    assert region([]) == ["us"]


def test_clean_url_strips_tracking():
    assert clean_url("https://x.com/job/1?utm_source=Simplify&ref=Simplify") == "https://x.com/job/1"
    assert clean_url("https://x.com/job?id=7&utm_source=Simplify") == "https://x.com/job?id=7"


def test_load_filters_and_sorts():
    rows = load_simplify(write([
        listing("Software Engineer Intern", days_ago=3),
        listing("AI Engineer Intern", company="Beta", days_ago=1),
        listing("Old Intern", days_ago=400),
        listing("Closed Intern", active=False),
        listing("Hidden Intern", visible=False),
        listing("Past Intern", terms=["Summer 2025"]),
        listing("Software Engineer Intern", days_ago=3),  # duplicate
    ]), now=NOW)
    assert [r["title"] for r in rows] == ["AI Engineer Intern", "Software Engineer Intern"]
    assert rows[0]["role"] == "ai" and rows[0]["ats"] == "Greenhouse"
    assert "utm_" not in rows[0]["url"]


def test_stats_counts_recent_activity():
    rows = load_simplify(write([listing(f"SWE Intern {i}", days_ago=i) for i in range(10)]), now=NOW)
    s = stats(rows, now=NOW)
    assert s["total"] == 10 and s["week"] == 7 and s["today"] == 1
    assert len(s["per_day"]) == 30 and sum(s["per_day"]) == 10


def test_atom_feed_is_valid_xml_and_escapes():
    rows = load_simplify(write([listing("R&D <Intern>", company="A&B")]), now=NOW)
    feed = atom_feed(rows, "Radar", "https://example.com/feed.xml", "https://example.com", NOW)
    root = ET.fromstring(feed)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    assert root.find("a:entry/a:title", ns).text == "A&B: R&D <Intern>"


def test_build_writes_site():
    out = pathlib.Path(tempfile.mkdtemp()) / "site"
    src = write([listing("AI Engineer Intern"), listing("Data Analyst Intern", company="Beta"),
                 listing("Evil </script><script>alert(1)</script> Intern", company="X")])
    st = build(out, src, now=NOW)
    assert st["total"] == 3
    for name in ("index.html", "postings.json", "feed.xml", "feed-ai.xml", "feed-data.xml", ".nojekyll"):
        assert (out / name).exists(), name
    page = (out / "index.html").read_text()
    assert "{{" not in page
    assert "</script><script>alert" not in page  # embedded data can't break out of its script tag
    data = json.loads((out / "postings.json").read_text())
    assert {p["role"] for p in data["postings"]} == {"ai", "data", "swe"}
