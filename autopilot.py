#!/usr/bin/env python3
"""Internship Autopilot command line.

  python3 autopilot.py init                     set up your personal files from the templates
  python3 autopilot.py doctor                   check your setup for gaps before a run
  python3 autopilot.py discover [--no-pull]     pull job lists, score them, write data/queue.csv
  python3 autopilot.py new --company ... --title ... --url ... --track ai_eng --form forms/x.json --jd-terms "a,b"
  python3 autopilot.py check packets/x.json     READY only if nothing needs you and every essay is approved
  python3 autopilot.py lint --text "..." --company Acme --jd "agents,evals"
  python3 autopilot.py track Submitted "Acme" "Software Engineer Intern" --term "Summer 2027" --note "confirmation page" --link URL
  python3 autopilot.py review export            drafts -> review-desk/drafts.json (open review-desk/index.html)
  python3 autopilot.py review import grades.json
"""
import argparse, json, shutil, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "lib"))


def cmd_init(a):
    pairs = [("templates/profile.example.json", "data/profile.json"),
             ("templates/stories.example.json", "data/stories.json"),
             ("templates/voice.example.md", "data/voice.md")]
    for src, dst in pairs:
        d = ROOT / dst
        if d.exists() and not a.force:
            print(f"keep   {dst} (exists)")
        else:
            d.parent.mkdir(parents=True, exist_ok=True); shutil.copy(ROOT / src, d); print(f"create {dst}")
    cache = ROOT / "data/answer_cache.json"
    if not cache.exists():
        cache.write_text("{}\n"); print("create data/answer_cache.json")
    import tracker
    tracker.open_book(); print(f"ready  {tracker.path().relative_to(ROOT)}")
    print("\nNext: fill in data/profile.json, data/stories.json and data/voice.md, put your resumes in resumes/,\n"
          "edit config/preferences.toml, then run `python3 autopilot.py doctor`.")


def cmd_doctor(a):
    from config import prefs, profile, stories
    problems, notes = [], []
    P = profile()
    if P["identity"]["email"].endswith("example.edu") or P["identity"]["first_name"] == "Jordan":
        problems.append("data/profile.json still has the example person in it")
    for t in prefs()["tracks"]:
        if not (ROOT / t["resume"]).exists():
            problems.append(f"track '{t['name']}': resume file {t['resume']} not found")
    conf = [s for s in stories() if s.get("status") == "confirmed"]
    if len(conf) < 3:
        problems.append(f"only {len(conf)} confirmed stories in data/stories.json (aim for 5 or more)")
    for s in conf:
        if not s.get("keywords"):
            notes.append(f"story '{s['id']}' has no keywords, so reuse across answers can't be detected")
    for k in ("grad_year", "grad_month", "school", "major", "gpa"):
        if not P["education"].get(k):
            problems.append(f"education.{k} is empty")
    if P.get("legal", {}).get("subject_to_noncompete") is None:
        notes.append("legal.subject_to_noncompete is unknown, so any non-compete question will pause and ask you")
    for p in problems: print("FIX   ", p)
    for n in notes: print("NOTE  ", n)
    print("OK, ready to run." if not problems else f"\n{len(problems)} thing(s) to fix before a run.")
    sys.exit(1 if problems else 0)


def cmd_discover(a):
    import discover
    discover.run(pull=not a.no_pull, top=a.top)


def cmd_new(a):
    import packets
    out = packets.new(a.company, a.title, a.url, a.track, a.form, a.jd_terms, a.pay, a.term)
    print("wrote", out.relative_to(ROOT))


def cmd_check(a):
    import packets
    ready, lines = packets.check(a.packet)
    print("\n".join(lines) or "nothing to flag")
    print("VERDICT:", "READY" if ready else "BLOCKED")
    sys.exit(0 if ready else 1)


def cmd_lint(a):
    import lint
    iss = lint.lint(a.text, a.company, [x.strip() for x in a.jd.split(",") if x.strip()])
    print(f"[{lint.status(iss)}]"); [print("   ", l, m) for l, m in iss]
    sys.exit(1 if lint.status(iss) == "BLOCK" else 0)


def cmd_track(a):
    import tracker
    r, updated = tracker.upsert(a.status, a.company, a.role, a.term, a.resume, a.pay, a.track, a.note, a.link)
    print(("updated" if updated else "added"), "row", r, a.company, "->", a.status)


def cmd_review(a):
    import review
    if a.action == "export":
        out, n = review.export(); print(f"{n} draft(s) -> {out.relative_to(ROOT)}. Open review-desk/index.html to grade.")
    else:
        if not a.file: sys.exit("usage: autopilot.py review import grades.json")
        print(review.import_grades(a.file))


def main():
    ap = argparse.ArgumentParser(description="Internship Autopilot"); sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init"); s.add_argument("--force", action="store_true"); s.set_defaults(f=cmd_init)
    s = sub.add_parser("doctor"); s.set_defaults(f=cmd_doctor)
    s = sub.add_parser("discover"); s.add_argument("--no-pull", action="store_true"); s.add_argument("--top", type=int, default=60); s.set_defaults(f=cmd_discover)
    s = sub.add_parser("new")
    for k in ("company", "title", "url", "form", "pay", "term", "jd-terms"): s.add_argument("--" + k, default="")
    s.add_argument("--track", required=True); s.set_defaults(f=cmd_new)
    s = sub.add_parser("check"); s.add_argument("packet"); s.set_defaults(f=cmd_check)
    s = sub.add_parser("lint"); s.add_argument("--text", required=True); s.add_argument("--company"); s.add_argument("--jd", default=""); s.set_defaults(f=cmd_lint)
    s = sub.add_parser("track"); s.add_argument("status"); s.add_argument("company"); s.add_argument("role")
    for k in ("term", "resume", "pay", "track", "note", "link"): s.add_argument("--" + k, default="")
    s.set_defaults(f=cmd_track)
    s = sub.add_parser("review"); s.add_argument("action", choices=["export", "import"]); s.add_argument("file", nargs="?"); s.set_defaults(f=cmd_review)
    a = ap.parse_args(); a.f(a)


if __name__ == "__main__":
    main()
