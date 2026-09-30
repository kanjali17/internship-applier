"""The local application tracker (data/tracker.xlsx). One row per company + role + term.

Columns: Status | Company | Role | Term | Date | Resume used | Listed pay | Track | Notes and evidence | Link / confirmation
The Status column gets a dropdown of the statuses in config/preferences.toml.
"""
import datetime, re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from config import ROOT, prefs, statuses

HEAD = ["Status", "Company", "Role", "Term", "Date", "Resume used", "Listed pay", "Track", "Notes and evidence", "Link / confirmation"]


def path():
    return ROOT / prefs()["tracker"]["path"]


def open_book():
    import openpyxl
    from openpyxl.worksheet.datavalidation import DataValidation
    p = path()
    if p.exists():
        return openpyxl.load_workbook(p)
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Applications"
    ws.append(HEAD)
    for c, w in zip("ABCDEFGHIJ", [30, 22, 44, 14, 12, 28, 14, 10, 60, 50]):
        ws.column_dimensions[c].width = w
    dv = DataValidation(type="list", formula1='"' + ",".join(statuses()) + '"', allow_blank=True)
    ws.add_data_validation(dv); dv.add("A2:A2000")
    ws.freeze_panes = "B2"
    p.parent.mkdir(parents=True, exist_ok=True); wb.save(p)
    return wb


def norm(title):
    t = re.sub(r"[\(\[].*?[\)\]]", "", (title or "").lower())
    t = re.sub(r"\b(20\d\d|summer|spring|winter|fall|intern(ship)?)\b|[-–,]", " ", t)
    return " ".join(t.split())


def rows():
    ws = open_book().active
    return [dict(zip(HEAD, r), _row=i) for i, r in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2) if r[1]]


def find(company, role):
    c, n = company.lower().strip(), norm(role)
    return next((r for r in rows() if (r["Company"] or "").lower().strip() == c and norm(r["Role"]) == n), None)


def upsert(status, company, role, term="", resume="", pay="", track="", note="", link="", date=None):
    if status not in statuses():
        raise SystemExit(f"Unknown status '{status}'. Use one of: {', '.join(statuses())}")
    wb = open_book(); ws = wb.active
    hit = find(company, role)
    r = hit["_row"] if hit else ws.max_row + 1
    date = date or datetime.date.today().isoformat()
    old_note = ws.cell(r, 9).value if hit else ""
    vals = [status, company, role, term, date, resume, pay, track,
            f"{date}: {note}" + (f" || {old_note}" if old_note else "") if note else old_note, link]
    for i, v in enumerate(vals, 1):
        if v not in (None, "") or not hit:
            ws.cell(r, i, v)
    wb.save(path())
    return r, bool(hit)
