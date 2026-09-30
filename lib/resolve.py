"""Form-question resolver: maps each application question to an answer WITH a source.

Resolution order:
  consent -> identity -> EEO -> work authorization (sponsorship before authorization before
  citizenship) -> education -> logistics -> essay (drafted per job) -> verified cache -> UNKNOWN

Every answer comes from data/profile.json (or the verified answer cache). Nothing is guessed:
a required question with no source returns action="pause" so Claude asks you.

Matching is whole-word ('state' must not match 'United States', 'no' must not match 'Non-citizen').
Dropdowns never default to the first option.

Input:  {"label": str, "type": "text|textarea|select|multi|checkbox|file|radio", "options": [str], "required": bool}
Output: {"label","kind","answer","source","confidence","action","required"}
        action in {fill, draft, pause, skip, upload}
"""
import json, re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from config import ROOT, profile

CACHE_PATH = ROOT / "data/answer_cache.json"
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]
SELECTS = ("checkbox", "select", "radio", "multi", "multi_value_single_select", "multi_value_multi_select")


def has(label, *words):
    l = label.lower()
    return any(re.search(r"(?<![a-z])" + re.escape(w.lower()) + r"(?![a-z])", l) for w in words)


YES = ["yes", "i do", "i have", "i am", "agree", "true", "authorized", "i acknowledge", "acknowledge"]
NO = ["no", "i do not", "i don't", "i am not", "false", "not required", "will not"]
NEG = ["no", "i do not", "i don't", "i am not", "not "]
DECLINE = ["decline", "prefer not", "do not wish", "don't wish", "choose not", "not to answer", "not to disclose"]


def pick(options, want):
    """want: 'yes' | 'no' | 'decline' | a literal option. Returns an exact option label, or None."""
    if not options:
        return want.capitalize() if want in ("yes", "no") else want
    opts = [(o, re.sub(r"\s+", " ", o.lower().strip())) for o in options]
    if want == "yes":
        for o, lo in opts:
            if any(re.match(re.escape(g) + r"\b", lo) for g in YES) and not any(re.match(re.escape(n) + r"\b", lo) for n in NEG) \
                    and not any(d in lo for d in DECLINE):
                return o
        return None
    if want == "no":
        for o, lo in opts:
            if any(re.match(re.escape(g) + r"\b", lo) for g in NO) and not any(d in lo for d in DECLINE):
                return o
        return None
    if want == "decline":
        return next((o for o, lo in opts if any(d in lo for d in DECLINE)), None)
    w = want.lower()
    for o, lo in opts:
        if lo == w:
            return o
    for o, lo in opts:
        if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", lo):
            return o
    return None


def pick_any(options, wants):
    for w in wants:
        a = pick(options, w)
        if a:
            return a
    return None


def as_list(v):
    return v if isinstance(v, list) else [v]


def grad():
    E = profile()["education"]
    return int(E["grad_year"]), int(E["grad_month"])


def grad_term():
    y, m = grad()
    season = "Spring" if m <= 5 else "Summer" if m <= 8 else "Fall"
    return f"{season} {y}", f"{MONTHS[m - 1].capitalize()} {y}"


CONSENT_WORDS = ["certify", "attest", "consent", "i agree", "agree to", "acknowledge", "true and complete",
                 "privacy notice", "privacy policy", "terms of service", "terms of use", "terms and conditions",
                 "accurate and complete", "information provided is accurate", "is accurate", "accuracy", "double-check",
                 "ai screening", "automated"]
# Legal items that each map to a consent flag. Unknown/false -> pause (or decline where declining is safe).
HARD = {
    "arbitration": "arbitration_agreement",
    "background check": "background_check_acknowledgement",
    "background screening": "background_check_acknowledgement",
    "consumer report": "background_check_acknowledgement",
    "retain my": "data_retention_beyond_role",
    "data retention": "data_retention_beyond_role",
    "record": "ai_interview_recording",
    "transcri": "ai_interview_recording",
    "sms": "sms_opt_in",
    "text message": "sms_opt_in",
    "future opportunities": "future_opportunities_contact",
    "future job": "future_opportunities_contact",
    "talent community": "future_opportunities_contact",
}
DECLINABLE = {"sms_opt_in", "future_opportunities_contact"}


def resolve(q, job):
    P = profile()
    L, t, opts = q["label"], q.get("type", "text"), q.get("options") or []
    ll = L.lower()

    def out(kind, ans, src, conf=1.0, action="fill"):
        return {"label": L, "kind": kind, "answer": ans, "source": src, "confidence": conf,
                "action": action, "required": q.get("required", False)}

    I, E, W, G = P["identity"], P["education"], P["work_auth"], P["logistics"]
    C, EEO, LEG = P.get("consents", {}), P.get("eeo_voluntary", {}), P.get("legal", {})

    # 1. consent / legal
    if has(L, "non-compete", "noncompete", "restrictive covenant", "non-solicitation"):
        v = LEG.get("subject_to_noncompete")
        if v is None:
            return out("legal", None, "legal.subject_to_noncompete unknown: ask", 0, "pause")
        return out("legal", pick(opts, "yes" if v else "no"), "legal.subject_to_noncompete")
    if has(L, "felony", "convicted", "criminal"):
        v = LEG.get("criminal_record_question")
        return out("legal", v, "legal.criminal_record_question", 1, "fill") if v else out("legal", None, "not in profile: ask", 0, "pause")
    hard = next((flag for w, flag in HARD.items() if w in ll), None)
    if hard and t in SELECTS:
        if C.get(hard):
            return out("consent", pick(opts, "yes") or (opts[0] if len(opts) == 1 else None), f"consents.{hard}=true", 0.95)
        if hard in DECLINABLE:
            a = pick(opts, "no")
            if a or t == "checkbox":
                return out("consent", a, f"consents.{hard}=false -> decline", 1, "fill" if a else "skip")
        return out("consent", None, f"consents.{hard} not approved: ask", 0, "pause")
    if any(w in ll for w in CONSENT_WORDS) and t in SELECTS:
        optxt = " ".join(opts).lower()
        ok = (("privacy" in ll or "privacy" in optxt) and C.get("privacy_notice_acknowledgement")) or \
             (any(w in ll for w in ["accurate", "accuracy", "double-check", "true and complete", "certify", "attest"]) and C.get("certify_true_and_complete")) or \
             (has(L, "terms of service", "terms of use", "terms and conditions") and C.get("ats_terms_of_service")) or \
             (has(L, "ai screening", "automated") and C.get("ai_screening_notice")) or \
             (has(L, "demographic", "self-identification", "self identification") and C.get("demographic_data_processing"))
        if ok:
            a = pick(opts, "yes") or (opts[0] if len(opts) == 1 else None)
            return out("consent", a or "checked", "consents (standard acknowledgement)", 0.95)
        return out("consent", None, "consent not pre-approved: ask", 0, "pause")

    if re.match(r"\s*if (yes|other|so|you answered|you selected)", ll):
        return out("conditional", None, "conditional follow-up; only answer if the parent answer calls for it", 1, "skip")

    # 2. identity
    if has(L, "first name", "given name") and not has(L, "preferred"): return out("identity", I["first_name"], "identity.first_name")
    if has(L, "preferred name", "preferred first name"): return out("identity", I.get("preferred_name") or I["first_name"], "identity.preferred_name")
    if has(L, "last name", "family name", "surname"): return out("identity", I["last_name"], "identity.last_name")
    if has(L, "full name", "legal name") or ll.strip() == "name": return out("identity", I["full_name"], "identity.full_name")
    if has(L, "email"): return out("identity", I["email"], "identity.email")
    if has(L, "phone", "mobile"): return out("identity", I["phone"], "identity.phone")
    if has(L, "linkedin"): return out("identity", I.get("linkedin"), "identity.linkedin", 1, "fill" if I.get("linkedin") else "skip")
    if has(L, "github"): return out("identity", I.get("github"), "identity.github", 1, "fill" if I.get("github") else "skip")
    if has(L, "portfolio", "website", "personal site"): return out("identity", I.get("portfolio"), "identity.portfolio", 1, "fill" if I.get("portfolio") else "skip")
    if has(L, "pronoun", "pronouns"):
        pr = I.get("pronouns")
        if not pr: return out("identity", None, "not in profile", 1, "skip")
        a = pick_any(opts, [pr, pr.split("/")[0]]) if opts else pr
        return out("identity", a, "identity.pronouns", 1 if a else 0, "fill" if a else "skip")
    if has(L, "resume", "cv") and t == "file": return out("file", job.get("resume_file"), "track resume", 1, "upload")
    if has(L, "cover letter"): return out("file", None, "optional; skipped unless required", 1, "draft" if q.get("required") else "skip")
    if has(L, "transcript"): return out("file", None, "transcript: ask for the file if required", 0, "pause" if q.get("required") else "skip")

    # 3. EEO (voluntary): values are lists of labels to try, or yes/no/decline
    def eeo(key, specific_no=()):
        v = EEO.get(key, "decline")
        if isinstance(v, list):
            a = pick_any(opts, v) if opts else v[0]
            if not a: a = pick(opts, "decline")
        elif v == "no":
            a = pick_any(opts, list(specific_no) + ["no"]) if opts else "No"
        else:
            a = pick(opts, v) if opts else None
        return out("eeo", a, f"eeo_voluntary.{key}", 1 if a else 0, "fill" if a else "skip")
    if has(L, "transgender"): return eeo("transgender")
    if has(L, "sexual orientation"): return eeo("sexual_orientation")
    if has(L, "gender", "sex") and not has(L, "orientation"): return eeo("gender")
    if has(L, "hispanic", "latino", "latinx"): return eeo("hispanic_latino")
    if has(L, "race", "ethnicity", "racial", "ethnic"): return eeo("race_ethnicity")
    if has(L, "veteran", "armed forces"): return eeo("veteran", ["I am not a protected veteran", "No, I am not a veteran"])
    if has(L, "disability"): return eeo("disability", ["No, I do not have a disability"])

    # 4. work authorization: sponsorship BEFORE authorization BEFORE citizenship
    if has(L, "sponsor", "sponsorship", "h-1b", "h1b", "visa"):
        return out("auth", pick(opts, "yes" if W["requires_sponsorship"] else "no"), f"work_auth.requires_sponsorship={W['requires_sponsorship']}")
    if has(L, "basis of your work authorization", "describes your work authorization", "your authorization to work") or \
            (opts and any("nationality" in o.lower() or "work permit" in o.lower() for o in opts)):
        a = pick_any(opts, W.get("authorization_basis_options", [])) if opts else None
        return out("auth", a, "work_auth.authorization_basis_options", 0.95 if a else 0, "fill" if a else "pause")
    if has(L, "authorized", "authorization", "legally eligible", "eligible to work", "right to work"):
        return out("auth", pick(opts, "yes" if W["authorized_us"] else "no"), f"work_auth.authorized_us={W['authorized_us']}")
    if has(L, "citizen", "citizenship", "permanent resident", "u.s. person", "us person", "itar", "export", "protected individual"):
        if W.get("us_citizen"):
            a = pick_any(opts, ["U.S. citizen", "US citizen", "United States Citizen", "citizen", "yes"]) if opts else "U.S. citizen"
            return out("auth", a, "work_auth.us_citizen=true", 0.9 if a else 0, "fill" if a else "pause")
        if W.get("us_person_export_control") and has(L, "u.s. person", "us person", "itar", "export"):
            return out("auth", pick(opts, "yes"), "work_auth.us_person_export_control=true", 0.9)
        return out("auth", None, "citizenship detail: ask", 0, "pause")
    if has(L, "clearance"):
        return out("auth", pick(opts, "no") or "No" if W.get("security_clearance", "none") == "none" else None, "work_auth.security_clearance")

    # 5. education (graduation windows compared against your grad month/year)
    gy, gm = grad()
    term, month_year = grad_term()
    dates = [(int(y), MONTHS.index(m) + 1) for m, y in re.findall(r"(" + "|".join(MONTHS) + r")\s+(\d{4})", ll)]
    if has(L, "graduate", "graduation", "graduating") and has(L, "between") and len(dates) >= 2:
        inside = dates[0] <= (gy, gm) <= dates[1]
        return out("edu", pick(opts, "yes" if inside else "no"), f"education.grad {month_year} within {dates[0]}..{dates[1]}", 0.95)
    if has(L, "graduating before", "graduate before", "graduating by", "graduate by", "graduating after", "graduate after") and dates:
        cutoff = dates[0]
        ans = (gy, gm) < cutoff if has(L, "before", "by") else (gy, gm) > cutoff
        return out("edu", pick(opts, "yes" if ans else "no"), f"education.grad {month_year} vs {cutoff}", 0.95)
    if has(L, "graduation", "grad date", "expected graduation", "graduate", "graduation year") and not has(L, "before", "after"):
        if opts:
            a = pick_any(opts, [month_year, term]) or next((o for o in opts if str(gy) in o and re.search(MONTHS[gm - 1][:3], o.lower())), None) \
                or next((o for o in opts if re.search(rf"{gy}\s*(&|and)?\s*(later|after)", o.lower())), None) or pick(opts, str(gy))
            return out("edu", a, "education.grad_year/grad_month", 0.9 if a else 0, "fill" if a else "pause")
        return out("edu", month_year, "education.grad_year/grad_month")
    if has(L, "school", "university", "college", "institution"):
        a = pick_any(opts, [E["school"]] + E.get("school_aliases", [])) if opts else E["school"]
        return out("edu", a, "education.school", 1 if a else 0, "fill" if a else "pause")
    if has(L, "degree") and not has(L, "discipline", "major", "field"):
        a = pick_any(opts, E.get("degree_options", []) + [E["degree"]]) if opts else E["degree"]
        return out("edu", a, "education.degree", 1 if a else 0, "fill" if a else "pause")
    if has(L, "discipline", "major", "field of study", "area of study"):
        if opts:
            for d in E.get("discipline_dropdown_order", [E["major"]]):
                a = pick(opts, d)
                if a: return out("edu", a, f"education.discipline_dropdown_order ({d})", 0.9)
            return out("edu", None, "no matching discipline option", 0, "pause")
        return out("edu", E["major"], "education.major")
    if has(L, "gpa", "grade point"):
        if has(L, "cumulative") and "cumulative" not in E.get("gpa_scope", "").lower():
            return out("edu", None, f"asks cumulative GPA; profile scope is '{E.get('gpa_scope')}': ask", 0, "pause")
        if opts:
            g = float(E["gpa"])
            a = next((o for o in opts if (m := re.findall(r"\d\.\d+", o)) and (float(m[0]) <= g <= float(m[-1]) if len(m) > 1 else abs(float(m[0]) - g) < 0.05)), None)
            return out("edu", a, "education.gpa", 0.9 if a else 0, "fill" if a else "pause")
        return out("edu", E["gpa"], "education.gpa", 0.8)
    if has(L, "start date", "start year", "began") and has(L, "school", "education", "degree", "program"):
        y, m = E["start"].split("-")
        return out("edu", f"{m}/{y}", "education.start")
    if has(L, "class standing", "year in school", "academic year", "class year"):
        return out("edu", pick(opts, E.get("class_standing", "")) if opts else E.get("class_standing"), "education.class_standing", 0.9)

    # 6. logistics
    if has(L, "relocate", "relocation"): return out("logistics", pick(opts, "yes" if G["willing_to_relocate"] else "no"), "logistics.willing_to_relocate")
    if has(L, "onsite", "on-site", "in office", "in-office", "days/week", "days a week", "days per week", "hybrid"):
        return out("logistics", pick(opts, "yes" if G["onsite_ok"] else "no"), "logistics.onsite_ok", 0.9)
    if opts and has(L, "which term", "which session", "term works", "internship term"):
        a = pick_any(opts, G.get("available_terms", []))
        return out("logistics", a, "logistics.available_terms", 0.95 if a else 0, "fill" if a else "pause")
    if has(L, "location preference", "preferred location", "preferred office", "which office", "which location"):
        if opts:
            a = pick_any(opts, G.get("location_preference_order", []))
            if a: return out("logistics", a, "logistics.location_preference_order", 0.9)
            return out("logistics", None, "no preferred location offered", 0, "pause")
        return out("logistics", ", then ".join(G.get("location_preference_order", [])[:3]), "logistics.location_preference_order", 0.8)
    if has(L, "following states", "these states", "any of the following states"):
        inside = I["state"].lower() in ll
        return out("logistics", pick(opts, "yes" if inside else "no"), f"identity.state={I['state']} vs listed states", 0.95)
    if opts and has(L, "countries", "based in", "which country", "country of residence"):
        a = pick(opts, I["country"])
        return out("logistics", a, "identity.country", 1 if a else 0, "fill" if a else "pause")
    if has(L, "current location", "where are you located", "city"): return out("logistics", f"{I['city']}, {I['state_abbr']}", "identity.city")
    if has(L, "address"):
        return out("logistics", I.get("address_line1") if q.get("required") else None, "identity.address (only when required)", 1, "fill" if q.get("required") else "skip")
    if has(L, "zip", "postal"): return out("logistics", I["postal_code"], "identity.postal_code")
    if has(L, "state") and not has(L, "united states", "statement"): return out("logistics", pick(opts, I["state"]) or I["state"], "identity.state")
    if has(L, "country"): return out("logistics", pick(opts, I["country"]) or I["country"], "identity.country")
    if has(L, "salary", "compensation", "pay expectation", "hourly rate", "expected pay", "desired pay"):
        pay = job.get("pay")
        return out("logistics", f"{pay}, as listed in the posting" if pay else "Flexible, in line with your intern pay band", "logistics.salary_rule", 0.8)
    if has(L, "how did you hear", "how did you find", "how did you learn", "where did you first hear", "source"):
        a = pick_any(opts, G.get("how_did_you_hear_order", [])) if opts else G.get("how_did_you_hear_text")
        return out("logistics", a, "logistics.how_did_you_hear", 0.8 if a else 0, "fill" if a else "pause")
    if has(L, "referred", "referral", "know anyone", "relatives", "family members"): return out("logistics", pick(opts, "no") or "No", "no referral / relatives on file")
    if has(L, "previously worked", "worked for", "employed by", "former employee", "previously employed", "worked at"):
        prev = (job.get("company") or "").lower() in [c.lower() for c in G.get("previously_employed_by", [])]
        return out("logistics", pick(opts, "yes" if prev else "no"), "logistics.previously_employed_by")
    if has(L, "previously applied", "applied before"):
        return out("logistics", None, "check the tracker, then answer", 0, "pause")
    if has(L, "prior internship", "number of internships", "previous internships"):
        n = str(G.get("prior_internships_count", 0))
        return out("logistics", pick(opts, n) or n, "logistics.prior_internships_count", 0.8)
    if has(L, "18 years", "at least 18", "18 or older"): return out("logistics", pick(opts, "yes" if G.get("age_18_plus") else "no"), "logistics.age_18_plus")
    if has(L, "current employer", "current company"):
        v = G.get("current_employer")
        return out("logistics", v or None, "logistics.current_employer", 1, "fill" if v else "skip")
    if has(L, "current title", "job title"):
        v = G.get("current_title_by_track", {}).get(job.get("track", ""))
        return out("logistics", v or None, "logistics.current_title_by_track", 0.9, "fill" if v else "skip")

    # 7. essays -> drafted per job from stories.json + voice.md, then linted and approved
    if t == "textarea" or (t in ("text", "input_text") and has(L, "why", "tell us", "describe", "what are you most", "project", "excited", "share something")):
        return out("essay", None, "draft from stories.json + voice.md; lint must PASS; needs your approval", 0.0, "draft")

    # 8. cache of answers you've confirmed before
    cache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}
    key = ll.strip() + "|" + "|".join(sorted(o.lower() for o in opts))
    if key in cache and cache[key].get("verified"):
        return out("cached", cache[key]["answer"], "answer_cache (verified)", 0.9)

    # 9. unknown: optional -> blank; required -> ask
    if not q.get("required"):
        return out("unknown", None, "optional, no source -> leave blank", 1, "skip")
    return out("unknown", None, "no source: ask", 0, "pause")


if __name__ == "__main__":
    qs = json.loads(pathlib.Path(sys.argv[1]).read_text())
    job = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    for q in qs:
        r = resolve(q, job)
        print(f"{r['action']:6} {r['kind']:9} {str(r['answer'])[:40]:40} <- {r['label'][:60]}  [{r['source']}]")
