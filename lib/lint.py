"""Truthfulness + authenticity gate for essay answers. Rules come from config/writing.toml.

  python3 lib/lint.py packets/foo.json                          # every essay in a packet
  python3 lib/lint.py --text "answer" --company Acme --jd "agents, evals"

Exit 0 = all pass (warnings allowed), 1 = at least one BLOCK. A BLOCKed answer is never submitted.
"""
import json, re, sys, argparse, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from config import profile, stories, writing


def allowed_numbers():
    blob = json.dumps(stories()) + json.dumps(profile())
    return set(re.findall(r"\d+(?:\.\d+)?", blob))


def known_tech():
    skills = profile().get("skills", {})
    return {t.lower() for k, grp in skills.items() if isinstance(grp, list) and k != "unverified" for t in grp}


def lint(text, company=None, jd_terms=None, max_sentences=None, min_sentences=None):
    W = writing()
    issues, low = [], text.lower()
    if W.get("block_dashes", True) and ("—" in text or re.search(r"\s–\s", text) or " -- " in text or re.search(r"\w - \w", text)):
        issues.append(("BLOCK", "dash used as punctuation (em/en dash or spaced hyphen)"))
    for b in W.get("banned", []):
        if re.search(r"(?<![\w-])" + re.escape(b) + r"(?![\w-])", low):
            issues.append(("BLOCK", f"banned phrase: '{b}'"))
    for p in W.get("warn_patterns", []):
        if re.search(p["pattern"], low):
            issues.append(("WARN", p["name"]))
    ok_nums, safe = allowed_numbers(), set(W.get("safe_numbers", []))
    for n in re.findall(r"(?<![\w.])\d+(?:\.\d+)?%?", text):
        core = n.rstrip("%")
        if core not in ok_nums and core not in safe:
            issues.append(("BLOCK", f"number '{n}' isn't in stories/profile (possible fabrication)"))
    if W.get("block_years_claims", True) and re.search(r"\b\d+\+?\s+(?:years?|yrs)\b", low):
        issues.append(("BLOCK", "claims N years of experience"))
    kt = known_tech()
    for t in W.get("suspect_tech", []):
        if re.search(r"(?<![\w])" + re.escape(t) + r"(?![a-z])", low) and t not in kt:
            issues.append(("WARN", f"mentions '{t}', which isn't in your skills. Fine for THEIR stack, never as your experience"))
    if company and low.count(company.lower()) > W.get("max_company_mentions", 2):
        issues.append(("WARN", f"company named {low.count(company.lower())} times"))
    if jd_terms and W.get("require_jd_term", True) and not any(j.lower() in low for j in jd_terms):
        issues.append(("BLOCK", "no specific detail from the job description (generic answer)"))
    sents = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
    if max_sentences and len(sents) > max_sentences:
        issues.append(("BLOCK", f"{len(sents)} sentences, limit {max_sentences}"))
    if min_sentences and len(sents) < min_sentences:
        issues.append(("WARN", f"{len(sents)} sentences, expected at least {min_sentences}"))
    for s in stories():
        if s.get("status") != "confirmed":
            for k in s.get("keywords", []):
                if k.lower() in low:
                    issues.append(("BLOCK", f"uses unconfirmed story '{s['id']}' ({k})"))
    for s in stories():
        for claim in s.get("do_not_claim", []):
            if len(claim) > 12 and claim.lower() in low:
                issues.append(("BLOCK", f"makes a claim you flagged as do-not-claim: '{claim}'"))
    return issues


def status(issues):
    return "BLOCK" if any(l == "BLOCK" for l, _ in issues) else ("WARN" if issues else "PASS")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("packet", nargs="?")
    ap.add_argument("--text"); ap.add_argument("--company"); ap.add_argument("--jd", default="")
    a = ap.parse_args()
    if a.packet:
        p = json.loads(pathlib.Path(a.packet).read_text())
        items = [(q["label"], q["answer"], q.get("max_sentences"), q.get("min_sentences"))
                 for q in p["answers"] if q.get("kind") == "essay" and q.get("answer")]
        company, jd = p["company"], p.get("jd_terms", [])
    else:
        items = [("text", a.text or "", None, None)]
        company, jd = a.company, [x.strip() for x in a.jd.split(",") if x.strip()]
    bad = False
    for label, text, mx, mn in items:
        iss = lint(text, company, jd, mx, mn)
        st = status(iss); bad |= st == "BLOCK"
        print(f"[{st}] {label[:80]}")
        for l, m in iss:
            print(f"    {l}: {m}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
