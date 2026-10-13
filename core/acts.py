"""Activities: types, progress, status, schedule queries and recurring occurrences."""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from core import db
from core.db import d, now_iso

KINDS = {
    "one_time": "One-time",
    "selected_dates": "Selected dates",
    "date_range": "Date range",
}
TYPE_CHOICES = ["One-time", "Selected dates", "Date range", "Recurring"]
FREQUENCIES = {"weekly": "Weekly", "monthly": "Monthly", "quarterly": "Quarterly"}
PRIORITIES = ["Low", "Normal", "High"]
STATUSES = ["Not started", "In progress", "Overdue", "Blocked", "Completed", "Cancelled"]


def type_label(a: dict) -> str:
    if a["recurring"]:
        return f"Recurring, {FREQUENCIES.get(a['frequency'], '').lower()}"
    return KINDS[a["kind"]]


def _today() -> date:
    return date.today()


def _date(v) -> date | None:
    return date.fromisoformat(v[:10]) if v else None


# --------------------------------------------------------------------------- loading
def load_all(include_cancelled: bool = True) -> list[dict]:
    acts = db.rows(
        "SELECT a.*, p.name AS lead_name FROM activities a LEFT JOIN people p ON p.id = a.lead_id "
        "ORDER BY COALESCE(a.start_date, '9999'), a.id")
    dates = db.rows("SELECT * FROM activity_dates ORDER BY day")
    support = db.rows("SELECT s.activity_id, p.id, p.name FROM activity_support s JOIN people p ON p.id = s.person_id")
    by_act: dict[int, list] = {}
    for r in dates:
        by_act.setdefault(r["activity_id"], []).append(r)
    sup: dict[int, list] = {}
    for r in support:
        sup.setdefault(r["activity_id"], []).append({"id": r["id"], "name": r["name"]})
    out = []
    for a in acts:
        a["dates"] = by_act.get(a["id"], [])
        a["support"] = sup.get(a["id"], [])
        enrich(a)
        if include_cancelled or a["status"] != "Cancelled":
            out.append(a)
    return out


def load(aid: int) -> dict | None:
    a = db.one("SELECT a.*, p.name AS lead_name FROM activities a LEFT JOIN people p ON p.id = a.lead_id "
               "WHERE a.id = ?", (aid,))
    if not a:
        return None
    a["dates"] = db.rows("SELECT * FROM activity_dates WHERE activity_id = ? ORDER BY day", (aid,))
    a["support"] = db.rows("SELECT p.id, p.name FROM activity_support s JOIN people p ON p.id = s.person_id "
                           "WHERE s.activity_id = ? ORDER BY p.name", (aid,))
    enrich(a)
    return a


def enrich(a: dict) -> dict:
    """Add progress, status, overdue dates and next date."""
    today = _today()
    if a["kind"] == "date_range":
        progress = int(a["progress"] or 0)
        overdue = bool(a["end_date"]) and _date(a["end_date"]) < today and progress < 100
        a["overdue_dates"] = [a["end_date"]] if overdue else []
        a["next_date"] = a["end_date"]
        a["done_count"], a["total_count"] = None, None
    else:
        total = len(a["dates"])
        done = sum(1 for x in a["dates"] if x["done"])
        progress = round(done / total * 100) if total else 0
        a["overdue_dates"] = [x["day"] for x in a["dates"] if not x["done"] and _date(x["day"]) < today]
        upcoming = [x["day"] for x in a["dates"] if not x["done"]]
        a["next_date"] = upcoming[0] if upcoming else None
        a["done_count"], a["total_count"] = done, total
    a["pct"] = progress
    if a["flag"] == "cancelled":
        status = "Cancelled"
    elif progress >= 100:
        status = "Completed"
    elif a["flag"] == "blocked":
        status = "Blocked"
    elif a["overdue_dates"]:
        status = "Overdue"
    elif progress > 0:
        status = "In progress"
    else:
        status = "Not started"
    a["status"] = status
    a["is_open"] = status not in ("Completed", "Cancelled")
    a["people_ids"] = ([a["lead_id"]] if a["lead_id"] else []) + [s["id"] for s in a["support"]]
    return a


def involves(a: dict, person_id: int | None) -> bool:
    return person_id is None or person_id in a["people_ids"]


def when_text(a: dict) -> str:
    fmt = lambda v: _date(v).strftime("%d %b %Y")  # noqa: E731
    if a["kind"] == "date_range":
        if a["start_date"] and a["end_date"]:
            return f"{fmt(a['start_date'])} to {fmt(a['end_date'])}"
        return "No dates set"
    if a["kind"] == "one_time":
        return fmt(a["dates"][0]["day"]) if a["dates"] else "No date set"
    n = len(a["dates"])
    if not n:
        return "No dates set"
    return f"{n} date{'s' if n != 1 else ''}, {fmt(a['dates'][0]['day'])} to {fmt(a['dates'][-1]['day'])}"


# --------------------------------------------------------------------------- range queries
def overlaps(a: dict, start: date, end: date) -> bool:
    if a["kind"] == "date_range":
        s, e = _date(a["start_date"]), _date(a["end_date"])
        return bool(s and e) and s <= end and e >= start
    return any(start <= _date(x["day"]) <= end for x in a["dates"])


def pending_items(acts: list[dict], start: date, end: date, person_id: int | None,
                  include_earlier_overdue: bool = True) -> list[dict]:
    """One row per outstanding piece of work in the period: a scheduled date, or a running date range."""
    items = []
    today = _today()
    for a in acts:
        if not a["is_open"] or not involves(a, person_id):
            continue
        if a["kind"] == "date_range":
            if overlaps(a, start, end) or (include_earlier_overdue and a["overdue_dates"]):
                items.append({"activity": a, "day": _date(a["end_date"]), "label": "Ends",
                              "overdue": bool(a["overdue_dates"])})
            continue
        for x in a["dates"]:
            if x["done"]:
                continue
            dd = _date(x["day"])
            in_period = start <= dd <= end
            earlier_overdue = include_earlier_overdue and dd < start and dd < today
            if in_period or earlier_overdue:
                items.append({"activity": a, "day": dd, "label": "Scheduled", "overdue": dd < today,
                              "date_id": x["id"]})
    items.sort(key=lambda i: (i["day"] or date.max, i["activity"]["title"]))
    return items


def period_progress(a: dict, start: date, end: date) -> tuple[int | None, int | None]:
    """For dated activities: (done, scheduled) within the period. None for date ranges."""
    if a["kind"] == "date_range":
        return None, None
    inside = [x for x in a["dates"] if start <= _date(x["day"]) <= end]
    return sum(1 for x in inside if x["done"]), len(inside)


def completed_in(acts: list[dict], start: date, end: date, person_id: int | None) -> int:
    """Scheduled dates marked done whose scheduled day is in the period, plus date ranges completed then."""
    n = 0
    for a in acts:
        if not involves(a, person_id):
            continue
        if a["kind"] == "date_range":
            if a["pct"] >= 100 and overlaps(a, start, end):
                n += 1
        else:
            n += sum(1 for x in a["dates"] if x["done"] and start <= _date(x["day"]) <= end)
    return n


# --------------------------------------------------------------------------- changes
def _log(con, aid: int, by: str, note: str, kind: str = "change") -> None:
    con.execute("INSERT INTO activity_log(activity_id, at, by_name, kind, note) VALUES (?,?,?,?,?)",
                (aid, now_iso(), by, kind, note))


def save(data: dict, by: str, aid: int | None = None) -> int:
    """Create or update an activity. data['days'] holds the dates for one-time / selected-dates kinds."""
    kind = data["kind"]
    days = sorted({d(x) for x in data.get("days", []) if x}) if kind != "date_range" else []
    start = days[0] if days else d(data.get("start_date"))
    end = days[-1] if days else d(data.get("end_date"))
    fields = {
        "ref": data.get("ref") or None, "title": data["title"].strip(), "description": data.get("description") or "",
        "kind": kind, "recurring": int(bool(data.get("recurring"))),
        "frequency": data.get("frequency") if data.get("recurring") else None,
        "start_date": start, "end_date": end, "lead_id": data.get("lead_id"),
        "priority": data.get("priority", "Normal"), "location": data.get("location") or "",
        "workplan_ref": data.get("workplan_ref") or "", "key_activity": int(bool(data.get("key_activity"))),
    }
    with db.connect(write=True) as con:
        if aid is None:
            cols = ", ".join([*fields, "created_by", "created_at", "updated_at"])
            marks = ", ".join("?" * (len(fields) + 3))
            cur = con.execute(f"INSERT INTO activities({cols}) VALUES ({marks})",
                              (*fields.values(), by, now_iso(), now_iso()))
            aid = cur.lastrowid
            if data.get("series_id"):
                con.execute("UPDATE activities SET series_id=? WHERE id=?", (data["series_id"], aid))
            _log(con, aid, by, data.get("log_note") or "Created this activity")
        else:
            before = dict(con.execute("SELECT * FROM activities WHERE id=?", (aid,)).fetchone())
            sets = ", ".join(f"{k} = ?" for k in fields)
            con.execute(f"UPDATE activities SET {sets}, updated_at = ? WHERE id = ?",
                        (*fields.values(), now_iso(), aid))
            changed = [k for k in fields if (before.get(k) or None) != (fields[k] or None)]
            labels = {"lead_id": "lead", "start_date": "dates", "end_date": "dates", "key_activity": "management visibility",
                      "workplan_ref": "workplan reference", "kind": "type", "recurring": "type", "frequency": "frequency"}
            names = sorted({labels.get(k, k.replace("_", " ")) for k in changed})
            if names:
                _log(con, aid, by, "Changed " + ", ".join(names))
        # dates
        if kind != "date_range":
            existing = {r["day"]: r for r in con.execute("SELECT * FROM activity_dates WHERE activity_id=?", (aid,))}
            for day in days:
                if day not in existing:
                    con.execute("INSERT INTO activity_dates(activity_id, day) VALUES (?,?)", (aid, day))
            for day, r in existing.items():
                if day not in days:
                    con.execute("DELETE FROM activity_dates WHERE id=?", (r["id"],))
        else:
            con.execute("DELETE FROM activity_dates WHERE activity_id=?", (aid,))
        # support people
        con.execute("DELETE FROM activity_support WHERE activity_id=?", (aid,))
        con.executemany("INSERT OR IGNORE INTO activity_support VALUES (?,?)",
                        [(aid, p) for p in data.get("support_ids", []) if p and p != data.get("lead_id")])
    return aid


def mark_date(date_id: int, done: bool, by: str, note: str = "") -> None:
    with db.connect(write=True) as con:
        r = con.execute("SELECT * FROM activity_dates WHERE id=?", (date_id,)).fetchone()
        if not r:
            return
        con.execute("UPDATE activity_dates SET done=?, done_at=?, done_by=?, note=? WHERE id=?",
                    (int(done), now_iso() if done else None, by if done else None,
                     ((note or "").strip() or None) if done else None, date_id))
        day = date.fromisoformat(r["day"]).strftime("%d %b %Y")
        msg = f"Marked {day} complete" if done else f"Reopened {day}"
        if done and note.strip():
            msg += f": {note.strip()}"
        _log(con, r["activity_id"], by, msg)
        con.execute("UPDATE activities SET updated_at=? WHERE id=?", (now_iso(), r["activity_id"]))


def set_progress(aid: int, pct: int, by: str, note: str = "") -> None:
    with db.connect(write=True) as con:
        old = con.execute("SELECT progress FROM activities WHERE id=?", (aid,)).fetchone()[0]
        con.execute("UPDATE activities SET progress=?, updated_at=? WHERE id=?", (pct, now_iso(), aid))
        msg = "Marked complete" if pct >= 100 else f"Progress {old}% to {pct}%"
        if note.strip():
            msg += f": {note.strip()}"
        _log(con, aid, by, msg)


def set_flag(aid: int, flag: str | None, by: str, reason: str = "") -> None:
    with db.connect(write=True) as con:
        con.execute("UPDATE activities SET flag=?, updated_at=? WHERE id=?", (flag, now_iso(), aid))
        msg = {"blocked": "Marked as blocked", "cancelled": "Cancelled the activity", None: "Cleared the blocked/cancelled flag"}[flag]
        if reason.strip():
            msg += f": {reason.strip()}"
        _log(con, aid, by, msg)


def add_note(aid: int, by: str, note: str) -> None:
    with db.connect(write=True) as con:
        _log(con, aid, by, note.strip(), "note")
        con.execute("UPDATE activities SET updated_at=? WHERE id=?", (now_iso(), aid))


def delete(aid: int) -> None:
    db.execute("DELETE FROM activities WHERE id=?", (aid,))


def log(aid: int) -> list[dict]:
    return db.rows("SELECT * FROM activity_log WHERE activity_id=? ORDER BY at DESC, id DESC", (aid,))


# --------------------------------------------------------------------------- recurring
def shift(day: date, frequency: str) -> date:
    if frequency == "weekly":
        return day + timedelta(days=7)
    months = 1 if frequency == "monthly" else 3
    m = day.month - 1 + months
    y, m = day.year + m // 12, m % 12 + 1
    last = calendar.monthrange(y, m)[1]
    # keep month-end dates at month end
    if day.day == calendar.monthrange(day.year, day.month)[1]:
        return date(y, m, last)
    return date(y, m, min(day.day, last))


def next_occurrence_preview(a: dict) -> dict:
    f = a["frequency"]
    if a["kind"] == "date_range":
        return {"start_date": shift(_date(a["start_date"]), f), "end_date": shift(_date(a["end_date"]), f), "days": []}
    return {"days": [shift(_date(x["day"]), f) for x in a["dates"]]}


def create_next_occurrence(a: dict, by: str) -> int:
    nxt = next_occurrence_preview(a)
    data = {
        "ref": a["ref"], "title": a["title"], "description": a["description"], "kind": a["kind"],
        "recurring": True, "frequency": a["frequency"], "lead_id": a["lead_id"],
        "support_ids": [s["id"] for s in a["support"]], "priority": a["priority"], "location": a["location"],
        "workplan_ref": a["workplan_ref"], "key_activity": a["key_activity"],
        "series_id": a["series_id"] or a["id"], "log_note": "Created as the next occurrence of a recurring activity",
        **nxt,
    }
    new_id = save(data, by)
    if not a["series_id"]:
        db.execute("UPDATE activities SET series_id=? WHERE id=?", (a["id"], a["id"]))
    with db.connect(write=True) as con:
        _log(con, a["id"], by, "Created the next occurrence")
    return new_id


def has_next_occurrence(a: dict) -> bool:
    series = a["series_id"] or a["id"]
    later = db.scalar("SELECT COUNT(*) FROM activities WHERE (series_id = ? OR id = ?) AND id <> ? "
                      "AND COALESCE(start_date,'') > COALESCE(?, '')", (series, series, a["id"], a["start_date"]))
    return bool(later)
