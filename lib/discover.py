"""Discovery: pull the public job lists in config/preferences.toml, filter and score them, write data/queue.csv.

Score = best track weight + company-tier bonus + location bonus + freshness, minus penalties.
Postings already in your tracker are marked DUP so they're never applied to twice.
"""
import csv, json, re, subprocess, sys, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from config import ROOT, prefs
import tracker

NOW = time.time()


def fetch_sources(pull=True):
    for s in prefs()["sources"]:
        d = ROOT / s["dir"]
        if not d.exists():
            print(f"cloning {s['name']} ...")
            subprocess.run(["git", "clone", "-q", "--depth", "1", s["repo"], str(d)], check=False)
        elif pull:
            subprocess.run(["git", "-C", str(d), "pull", "-q", "--depth", "1"], check=False)


def simplify_listings_json(src):
    S = prefs()["search"]
    p = ROOT / src["dir"] / ".github/scripts/listings.json"
    if not p.exists():
        return
    want = [t.lower() for t in S["terms"] + S.get("offcycle_terms", [])]
    for x in json.loads(p.read_text()):
        if not (x.get("active") and x.get("is_visible", True)):
            continue
        terms = " ".join(x.get("terms", []))
        if not any(w in terms.lower() for w in want):
            continue
        degs = [g.lower() for g in x.get("degrees", [])]
        key = re.sub(r"'s$", "", (S.get("degree") or "").lower())
        if degs and key and not any(key in g for g in degs):
            continue
        yield dict(source=src["name"], company=x["company_name"], title=x["title"], term=terms,
                   locations=x.get("locations", []), url=x["url"].split("?utm")[0], posted=x.get("date_posted"))


def zapply_readme(src):
    p = ROOT / src["dir"] / "README.md"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        m = re.match(r"\|\s*\*\*(.+?)\*\*\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|.*?\]\((https?://[^)]+)\)", line)
        if not m:
            continue
        co, title, loc, age, url = m.groups()
        a = None
        mm = re.match(r"(\d+)\s*(mo|m|h|d|w)", age.strip())
        if mm:
            n, u = int(mm.group(1)), mm.group(2)
            a = {"m": n / 1440, "h": n / 24, "d": n, "w": n * 7, "mo": n * 30}[u]
        tm = re.search(r"\b(spring|summer|fall|winter)\s*20\d\d\b", title, re.I)
        yield dict(source=src["name"], company=co, title=title, term=tm.group(0) if tm else "", locations=[loc],
                   url=url.split("?s=")[0], posted=NOW - a * 86400 if a is not None else None)


PARSERS = {"simplify_listings_json": simplify_listings_json, "zapply_readme": zapply_readme}


def score(x, age_days):
    P, S = prefs(), prefs()["search"]
    tl, cl, ll = x["title"].lower(), x["company"].lower(), " ".join(x["locations"]).lower()
    if re.search(S["exclude_title"], tl):
        return None, None, "excluded title"
    if S.get("exclude_locations") and re.search(S["exclude_locations"], ll) and not re.search(r"\b(us|usa|united states|remote)\b", ll):
        return None, None, "location"
    track, s = None, 0
    for t in P["tracks"]:
        if re.search(t["titles"], tl) and t["weight"] > s:
            track, s = t["name"], t["weight"]
    sticky = [t for t in P["tracks"] if t.get("sticky") and re.search(t["titles"], tl)]
    if sticky:
        track, s = sticky[0]["name"], max(s, sticky[0]["weight"])
    if not track:
        return None, None, "no track"
    if re.search(r"\b(research scientist|research intern|ai research)\b", tl):
        s -= 14  # usually graduate-leaning
    if not re.search(r"intern|co-?op", tl):
        s -= 15
    tier_hit = False
    tiers = P.get("company_tiers", [])
    top = S.get("offcycle_tiers") or ([tiers[0]["name"]] if tiers else [])
    for tier in tiers:
        if any(re.search(r"(?<![a-z])" + re.escape(c) + r"(?![a-z])", cl) for c in tier["companies"]):
            s += tier["bonus"]; tier_hit = tier["name"] in top; break
    off = [t.lower() for t in S.get("offcycle_terms", [])]
    if x.get("term") and not any(t.lower() in x["term"].lower() for t in S["terms"] + S.get("offcycle_terms", [])):
        return None, None, "term not wanted"
    if x.get("term") and any(o in x["term"].lower() for o in off) and not any(t.lower() in x["term"].lower() for t in S["terms"]):
        if S.get("offcycle_only_top_tier") and not tier_hit:
            return None, None, "off-cycle, not top tier"
        s -= 6
    s += max([l["bonus"] for l in P.get("locations", []) if re.search(l["match"], ll)] or [0])
    F = P.get("freshness", {})
    if age_days is not None:
        if age_days > S.get("max_age_days", 999):
            return None, None, "too old"
        s += F.get("days_3", 0) if age_days <= 3 else F.get("days_7", 0) if age_days <= 7 else \
            F.get("days_14", 0) if age_days <= 14 else F.get("days_30", 0) if age_days <= 30 else F.get("older", 0)
    return track, s, ""


def site(url):
    A = prefs().get("ats", {})
    u = url.lower()
    if "zapply.jobs/l/d/" in u:  # Zapply redirect slugs start with the ATS name
        u = u.split("/l/d/")[1].split("-")[0]
        u = {"workday": "myworkdayjobs", "ashby": "ashbyhq", "lever": "lever.co", "sr": "smartrecruiters", "oracle": "oraclecloud"}.get(u, u)
    if any(k in u for k in A.get("needs_account", [])):
        return "needs_account"
    if any(k in u for k in A.get("no_account", [])):
        return "no_account"
    return "other"


def run(pull=True, top=60):
    fetch_sources(pull)
    done = {(r["Company"] or "").lower().strip() + "|" + tracker.norm(r["Role"]) for r in tracker.rows()}
    seen, out, skipped = set(), [], 0
    for src in prefs()["sources"]:
        for x in PARSERS[src["kind"]](src):
            age = (NOW - x["posted"]) / 86400 if x["posted"] else None
            track, s, why = score(x, age)
            if track is None:
                skipped += 1; continue
            k = x["company"].lower().strip() + "|" + tracker.norm(x["title"])
            if k in seen:
                continue
            seen.add(k)
            out.append(dict(score=s, track=track, company=x["company"], title=x["title"], term=x["term"],
                            locations="; ".join(x["locations"])[:80], age_days=round(age, 1) if age is not None else "",
                            site=site(x["url"]), dup="DUP" if k in done else "", source=x["source"], url=x["url"]))
    out.sort(key=lambda r: (r["dup"] != "", -r["score"]))
    cap, per, ranked, overflow = prefs()["caps"]["per_company_30d"], {}, [], []
    for r in out:
        c = r["company"].lower()
        per[c] = per.get(c, 0) + 1
        (ranked if per[c] <= cap else overflow).append(r)
    out = ranked + overflow
    q = ROOT / "data/queue.csv"
    q.parent.mkdir(exist_ok=True)
    if out:
        with q.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    print(f"{len(out)} candidate roles ({skipped} filtered out) -> data/queue.csv")
    for r in [r for r in out if not r["dup"]][:top]:
        print(f"{r['score']:>3} {r['track']:7} {str(r['age_days']):>5}d {r['site']:13} {r['company'][:22]:22} {r['title'][:58]}")
    return out
