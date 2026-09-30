"""Review desk bridge. `export` writes every unapproved essay draft to review-desk/drafts.json;
open review-desk/index.html, grade, click Export, then `import` the grades file you downloaded.
Approved answers unlock their packet; rewrite notes go back to Claude; all grades are kept in
data/feedback/ so Claude can fold the patterns into data/voice.md."""
import datetime, json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from config import ROOT


def rid(packet_path, i):
    return f"{pathlib.Path(packet_path).stem}#{i}"


def export():
    items = []
    for p in sorted((ROOT / "packets").glob("*.json")):
        pk = json.loads(p.read_text())
        for i, a in enumerate(pk.get("answers", [])):
            if a.get("kind") == "essay" and a.get("answer") and a.get("review") != "approved":
                items.append(dict(id=rid(p, i), company=pk["company"], role=pk["title"], question=a["label"],
                                  answer=a["answer"], story=a.get("story", ""), note=a.get("note", ""),
                                  status=a.get("review", "draft")))
    out = ROOT / "review-desk/drafts.json"
    out.write_text(json.dumps({"exported": datetime.datetime.now().isoformat(timespec="minutes"), "items": items}, indent=2))
    return out, len(items)


def import_grades(path):
    g = json.loads(pathlib.Path(path).read_text())
    grades = g.get("grades", g)
    fb = ROOT / "data/feedback"; fb.mkdir(parents=True, exist_ok=True)
    (fb / f"grades_{datetime.date.today().isoformat()}.json").write_text(json.dumps(grades, indent=2))
    changed = {"approved": 0, "rewrite": 0}
    for key, grade in grades.items():
        stem, i = key.rsplit("#", 1)
        p = ROOT / "packets" / f"{stem}.json"
        if not p.exists():
            continue
        pk = json.loads(p.read_text())
        a = pk["answers"][int(i)]
        a["review"] = "approved" if grade.get("decision") == "approve" else "rewrite"
        a["grade"] = grade
        changed[a["review"]] += 1
        p.write_text(json.dumps(pk, indent=2))
    return changed
