from lint import lint, status

def test_blocks_cliches_and_dashes():
    assert status(lint("I am passionate about AI — truly.")) == "BLOCK"

def test_blocks_invented_numbers():
    assert status(lint("I cut latency by 73% on the search tool.")) == "BLOCK"

def test_allows_story_numbers():
    iss = lint("I wrote a 40-question benchmark for the search tool, and it answered 30 correctly.", "Acme", ["benchmark"])
    assert status(iss) != "BLOCK", iss

def test_blocks_unconfirmed_story():
    assert status(lint("I built a weather bot for fun.")) == "BLOCK"

def test_requires_jd_term():
    assert status(lint("I like building tools that help people.", "Acme", ["evals", "agents"])) == "BLOCK"

def test_blocks_years_claims():
    assert status(lint("I have 3 years of Python experience.")) == "BLOCK"
