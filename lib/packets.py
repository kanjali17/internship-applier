"""Application packets: one JSON per job holding every field's answer + its source, the resume,
essay drafts, and a READY / BLOCKED verdict. Claude only types what a READY packet says."""
import datetime, json, re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from config import ROOT, stories, writing, resume_for, tracks
from resolve import resolve
import lint as L
from overlap import check_packet


def slug(*xs):
    return re.sub(r"[^a-z0-9]+", "_", "_".join(xs).lower()).strip("_")[:60]


def suggest_stories(text, track, k=3):
    hints = writing().get("tag_hints", {})
    low = text.lower()
    want = {t for w, tags in hints.items() if w in low for t in tags} | {track}
    scored = sorted(((len(want & set(s.get("tags", []))), s["id"]) for s in stories() if s.get("status") == "confirmed"), reverse=True)
    return [sid for sc, sid in scored[:k] if sc > 0]


def new(company, title, url, track, form_path="", jd_terms="", pay="", term=""):
    if track not in tracks():
        raise SystemExit(f"Unknown track '{track}'. Tracks: {', '.join(tracks())}")
    form = json.loads(pathlib.Path(form_path).read_text()) if form_path else []
    job = dict(company=company, title=title, url=url, track=track, pay=pay, resume_file=resume_for(track))
    terms = [t.strip() for t in jd_terms.split(",") if t.strip()]
    answers = []
    for q in form:
        a = resolve(q, job) | {"type": q.get("type"), "options": q.get("options")}
        if a["kind"] == "essay":
            a["suggested_stories"] = suggest_stories(" ".join(terms) + " " + a["label"], track)
            m = re.search(r"(\d)\s*[-– to]+\s*(\d)\s*sentences", a["label"].lower())
            a["min_sentences"], a["max_sentences"] = (int(m.group(1)), int(m.group(2))) if m else (None, 8)
            a["review"] = "draft"
        answers.append(a)
    pk = dict(company=company, title=title, url=url, track=track, term=term, pay=pay, resume_file=resume_for(track),
              jd_terms=terms, created=datetime.date.today().isoformat(), answers=answers, status="draft")
    out = ROOT / "packets" / f"{slug(company, title)}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(pk, indent=2))
    return out


def check(path):
    """Returns (ready: bool, report lines). Ready = no pauses, every essay drafted, linted PASS/WARN,
    no story reused across answers, and every essay approved in the review desk."""
    pk = json.loads(pathlib.Path(path).read_text())
    lines, ready = [], True
    for a in pk["answers"]:
        if a["action"] == "pause":
            ready = False; lines.append(f"ASK YOU: {a['label'][:90]}  [{a['source']}]")
        elif a["action"] == "fill" and a.get("answer") in (None, "") and a.get("required"):
            ready = False; lines.append(f"NO OPTION MATCHED: {a['label'][:90]}")
        elif a["action"] == "fill" and a.get("confidence", 1) < 0.8:
            lines.append(f"LOW CONFIDENCE ({a['confidence']}): {a['label'][:70]} -> {a['answer']}")
        if a.get("kind") == "essay":
            if not a.get("answer"):
                if a.get("required") or a["action"] == "draft":
                    ready = False; lines.append(f"ESSAY NOT DRAFTED: {a['label'][:90]}")
                continue
            iss = L.lint(a["answer"], pk["company"], pk.get("jd_terms"), a.get("max_sentences"), a.get("min_sentences"))
            st = L.status(iss)
            lines.append(f"LINT {st}: {a['label'][:80]}" + "".join(f"\n    {l}: {m}" for l, m in iss))
            if st == "BLOCK":
                ready = False
            if a.get("review") != "approved":
                ready = False; lines.append(f"AWAITING YOUR APPROVAL ({a.get('review', 'draft')}): {a['label'][:70]}")
    for sid, labs in check_packet(pk).items():
        ready = False; lines.append(f"STORY '{sid}' USED IN MORE THAN ONE ANSWER: {labs}")
    pk["status"] = "ready" if ready else "blocked"
    pathlib.Path(path).write_text(json.dumps(pk, indent=2))
    return ready, lines
