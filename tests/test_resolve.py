from resolve import resolve, pick

JOB = {"company": "Acme", "track": "ai_eng", "pay": "$40/hr", "resume_file": "resumes/resume_ai_eng.pdf"}

def r(label, type="text", options=None, required=True):
    return resolve({"label": label, "type": type, "options": options or [], "required": required}, JOB)

def test_identity():
    assert r("First Name")["answer"] == "Jordan"
    assert r("Email")["answer"].endswith("example.edu")

def test_whole_word_matching():
    # 'state' must not trigger on 'United States'; 'no' must not pick 'Non-citizen'
    assert r("Country", "select", ["Canada", "United States"])["answer"] == "United States"
    assert pick(["Non-citizen", "No"], "no") == "No"

def test_sponsorship_before_authorization():
    a = r("Are you authorized to work in the US without visa sponsorship?", "select", ["Yes", "No"])
    assert a["source"].startswith("work_auth.requires_sponsorship")

def test_never_defaults_to_first_option():
    a = r("Which office?", "select", ["Tokyo", "Berlin"])
    assert a["answer"] is None and a["action"] == "pause"

def test_hard_consents_pause_or_decline():
    assert r("I consent to a background check", "checkbox", ["Yes"])["action"] == "pause"
    assert r("I agree to binding arbitration", "checkbox", ["I agree"])["action"] == "pause"
    sms = r("Opt in to SMS text messages?", "select", ["Yes", "No"])
    assert sms["answer"] == "No"

def test_standard_ack_is_filled():
    a = r("I certify that the information provided is accurate", "checkbox", ["I certify"])
    assert a["action"] == "fill"

def test_grad_window():
    # example profile graduates May 2027
    assert r("Are you graduating between December 2026 and June 2027?", "select", ["Yes", "No"])["answer"] == "Yes"
    assert r("Are you graduating between August 2027 and June 2028?", "select", ["Yes", "No"])["answer"] == "No"

def test_eeo_decline():
    a = r("Gender", "select", ["Male", "Female", "I decline to self-identify"], required=False)
    assert a["answer"] == "I decline to self-identify"

def test_unknown_required_pauses():
    assert r("What is your favorite dinosaur?", "select", ["T-rex", "Other"])["action"] == "pause"

def test_essay_is_drafted_not_filled():
    assert r("Why do you want to work here?", "textarea")["action"] == "draft"

def test_noncompete_unknown_pauses():
    assert r("Are you subject to a non-compete agreement?", "select", ["Yes", "No"])["action"] == "pause"

def test_gpa_range_option():
    a = r("GPA", "select", ["4.0", "3.5 - 3.9", "3.0 - 3.4"])
    assert a["answer"] == "3.5 - 3.9"
