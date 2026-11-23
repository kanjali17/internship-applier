"""Internship Radar: a public, auto-updating board of internship postings.

The autopilot ranks postings for ONE person. The radar publishes ALL current
postings as a static site anyone can use: filter by role, term, location and
freshness, see what's new since your last visit, keep a private list of what
you've applied to (stored in your browser), and subscribe to RSS/Atom feeds
per role. A GitHub Actions workflow rebuilds it every few hours and deploys it
to GitHub Pages, so there is no server to run or pay for.

    python3 autopilot.py radar build --out _site          # build from ext/ sources
    python3 autopilot.py radar build --out _site --listings path/to/listings.json

Stdlib only. Configuration lives in the [radar] table of preferences.toml.
"""
from __future__ import annotations

import html
import json
import re
import time
import pathlib
from collections import Counter
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape

from config import ROOT, prefs

DAY = 86400

# Role buckets shown on the board. Simplify's own category is the starting
# point; titles refine it (its "AI/ML/Data" lumps ML engineers with analysts).
ROLES = [
    ("pm", "Product", r"\b(product manag\w*|apm|technical program\w*|tpm|product owner|product intern|product analyst)\b"),
    ("quant", "Quant", r"\b(quant\w*|trading|trader)\b"),
    ("ai", "AI / ML", r"\b(ai|ml|machine learning|deep learning|llm|nlp|computer vision|genai|applied scien\w*|research scien\w*|foundation models?|agents?|agentic|autonomy)\b"),
    ("data", "Data", r"\b(data|analytics|analyst|business intelligence|bi)\b"),
    ("hardware", "Hardware", r"\b(hardware|electrical|embedded|firmware|fpga|asic|rtl|circuit|silicon|mechanical|robotics)\b"),
    ("swe", "Software", r"\b(software|swe|developer|engineer\w*|full[- ]?stack|backend|front[- ]?end|platform|devops|sre|security|mobile|ios|android|web)\b"),
]
ROLE_LABELS = {k: label for k, label, _ in ROLES} | {"other": "Other"}
CATEGORY_HINT = {"Product": "pm", "Product Management": "pm", "Quant": "quant", "Hardware": "hardware",
                 "Software": "swe", "Software Engineering": "swe"}

ATS = [("greenhouse", "Greenhouse"), ("lever.co", "Lever"), ("ashbyhq", "Ashby"), ("myworkdayjobs", "Workday"),
       ("icims", "iCIMS"), ("smartrecruiters", "SmartRecruiters"), ("rippling", "Rippling"), ("workable", "Workable"),
       ("jobvite", "Jobvite"), ("taleo", "Taleo"), ("successfactors", "SuccessFactors"), ("oraclecloud", "Oracle")]

# Locations are treated as US unless they name another country. The source
# mixes "Toronto, ON, Canada", "London, UK", "NYC" and bare state names, so
# looking for non-US markers is far more reliable than recognizing US ones.
NON_US = re.compile(
    r"\b(canada|uk|united kingdom|england|scotland|ireland|india|germany|france|netherlands|spain|italy|"
    r"switzerland|sweden|denmark|norway|finland|poland|israel|singapore|japan|china|hong kong|taiwan|korea|"
    r"australia|new zealand|brazil|mexico|argentina|chile|colombia|philippines|vietnam|indonesia|malaysia|"
    r"thailand|uae|dubai|saudi|egypt|nigeria|kenya|south africa|belgium|austria|portugal|czech|romania|hungary|"
    r"greece|turkey|luxembourg|estonia|ukraine|pakistan|bangladesh|sri lanka|costa rica|puerto rico)\b", re.I)


def settings() -> dict:
    defaults = {
        "title": "Internship Radar",
        "terms": ["Summer 2027", "Fall 2027", "Spring 2027", "Winter 2027", "Summer 2028"],
        "max_age_days": 120,
        "feed_size": 150,
        "site_url": "",
    }
    return defaults | prefs().get("radar", {})


def classify(title: str, category: str = "") -> str:
    """Pick a role bucket. Explicit title words beat the source's category."""
    t = title.lower()
    for key, _, pattern in ROLES[:-1]:  # everything but the generic "software" catch-all
        if re.search(pattern, t):
            # "Data" words inside an AI title ("ML Data Engineer") stay AI; checked first above.
            return key
    if category in CATEGORY_HINT:
        return CATEGORY_HINT[category]
    # The source files odd roles ("Pharmacy Aggregation Intern") under AI/ML/Data;
    # without an AI or data word in the title they're more honestly "Other".
    if re.search(ROLES[-1][2], t):
        return "swe"
    return "other"


def ats_name(url: str) -> str:
    u = url.lower()
    return next((name for key, name in ATS if key in u), "")


def region(locations: list[str]) -> list[str]:
    """Coarse location tags for filtering: remote, us, intl."""
    tags = set()
    for loc in locations:
        if "remote" in loc.lower():
            tags.add("remote")
        tags.add("intl" if NON_US.search(loc) else "us")
    return sorted(tags) or ["us"]


def clean_url(url: str) -> str:
    return re.sub(r"[?&](utm_[^&]+|ref=Simplify|src=Simplify)", "", url).rstrip("?&")


def load_simplify(path: pathlib.Path, now: float | None = None) -> list[dict]:
    """Read SimplifyJobs listings.json into board rows (active, visible, wanted terms, recent)."""
    now = now or time.time()
    cfg = settings()
    wanted = [t.lower() for t in cfg["terms"]]
    rows, seen = [], set()
    for x in json.loads(path.read_text()):
        if not (x.get("active") and x.get("is_visible", True)):
            continue
        terms = [t for t in x.get("terms", []) if t.lower() in wanted]
        if not terms:
            continue
        posted = x.get("date_posted") or x.get("date_updated") or now
        age = (now - posted) / DAY
        if age > cfg["max_age_days"]:
            continue
        url = clean_url(x.get("url", ""))
        key = (x["company_name"].strip().lower(), re.sub(r"\W+", " ", x["title"].lower()).strip(), tuple(terms))
        if key in seen or not url:
            continue
        seen.add(key)
        locs = [loc.strip() for loc in x.get("locations", []) if loc.strip()]
        rows.append({
            "id": x.get("id") or f"{key[0]}|{key[1]}",
            "company": x["company_name"].strip(),
            "title": x["title"].strip(),
            "role": classify(x["title"], x.get("category", "")),
            "terms": terms,
            "locations": locs,
            "region": region(locs),
            "posted": int(posted),
            "url": url,
            "ats": ats_name(url),
            "sponsorship": x.get("sponsorship", ""),
            "degrees": x.get("degrees", []),
        })
    rows.sort(key=lambda r: -r["posted"])
    return rows


def stats(rows: list[dict], now: float | None = None) -> dict:
    now = now or time.time()
    by_day = Counter()
    for r in rows:
        days_ago = int((now - r["posted"]) // DAY)
        if 0 <= days_ago < 30:
            by_day[days_ago] += 1
    week = [r for r in rows if now - r["posted"] < 7 * DAY]
    return {
        "total": len(rows),
        "today": sum(1 for r in rows if now - r["posted"] < DAY),
        "week": len(week),
        "companies": len({r["company"] for r in rows}),
        "per_day": [by_day.get(d, 0) for d in range(29, -1, -1)],  # oldest -> today
        "top_week": Counter(r["company"] for r in week).most_common(8),
        "roles": Counter(r["role"] for r in rows).most_common(),
    }


# ── output ──────────────────────────────────────────────────────────────────

def atom_feed(rows: list[dict], title: str, self_url: str, site_url: str, now: float) -> str:
    def ts(t: float) -> str:
        return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    entries = []
    for r in rows:
        where = "; ".join(r["locations"][:3]) or "Location not listed"
        summary = f"{r['company']} · {', '.join(r['terms'])} · {where}"
        entries.append(
            "<entry>"
            f"<title>{xml_escape(r['company'] + ': ' + r['title'])}</title>"
            f'<link href="{xml_escape(r["url"])}"/>'
            f"<id>urn:radar:{xml_escape(str(r['id']))}</id>"
            f"<updated>{ts(r['posted'])}</updated>"
            f"<category term=\"{r['role']}\"/>"
            f"<summary>{xml_escape(summary)}</summary>"
            "</entry>"
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        f"<title>{xml_escape(title)}</title>"
        f'<link href="{xml_escape(site_url or self_url)}"/>'
        f'<link rel="self" href="{xml_escape(self_url)}"/>'
        f"<id>{xml_escape(self_url or 'urn:radar:' + title)}</id>"
        f"<updated>{ts(now)}</updated>"
        + "".join(entries)
        + "</feed>\n"
    )


def build(out: pathlib.Path, listings: pathlib.Path | None = None, now: float | None = None) -> dict:
    """Write index.html, postings.json and Atom feeds into out/. Returns stats."""
    now = now or time.time()
    cfg = settings()
    if listings is None:
        src = next((s for s in prefs()["sources"] if s["kind"] == "simplify_listings_json"), None)
        if src is None:
            raise SystemExit("radar: no simplify_listings_json source in preferences")
        listings = ROOT / src["dir"] / ".github/scripts/listings.json"
    if not listings.exists():
        raise SystemExit(f"radar: {listings} not found; run `python3 autopilot.py discover` once to fetch sources")
    rows = load_simplify(listings, now)
    st = stats(rows, now)
    out.mkdir(parents=True, exist_ok=True)

    payload = {"generated": int(now), "roles": ROLE_LABELS, "terms": cfg["terms"], "stats": st, "postings": rows}
    (out / "postings.json").write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))

    base = cfg["site_url"].rstrip("/")
    feeds = {"": "All roles"} | {k: v for k, v in ROLE_LABELS.items() if k != "other"}
    for key, label in feeds.items():
        name = f"feed-{key}.xml" if key else "feed.xml"
        subset = [r for r in rows if not key or r["role"] == key][: cfg["feed_size"]]
        (out / name).write_text(atom_feed(subset, f"{cfg['title']}: {label}", f"{base}/{name}" if base else name, base, now))

    template = (ROOT / "radar/index.html").read_text()
    page = (template
            .replace("{{TITLE}}", html.escape(cfg["title"]))
            .replace("{{GENERATED}}", datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
            .replace("{{DATA}}", json.dumps(payload, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")))
    (out / "index.html").write_text(page)
    (out / ".nojekyll").write_text("")
    return st
