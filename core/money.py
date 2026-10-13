"""Budget, spending ledger, invoices sent to the partner, and instalments received."""
from __future__ import annotations

from datetime import date

from core import db
from core.db import d, now_iso

PAY_METHODS = ["Bank transfer", "Cash", "Cheque", "Mobile money"]
INVOICE_KINDS = ["Funds request", "Invoice", "Financial report"]
INVOICE_STATUS = ["Sent", "Approved", "Paid", "Returned for correction"]


def rate() -> float:
    try:
        return float(db.settings()["alt_rate"] or 0) or 1.0
    except ValueError:
        return 1.0


def lines() -> list[dict]:
    return db.rows("SELECT * FROM budget_lines ORDER BY sort, id")


def line_summary(until: date | None = None) -> list[dict]:
    """Every budget line with spending to date."""
    cond, params = ("WHERE e.day <= ?", (d(until),)) if until else ("", ())
    spent = {r["line_id"]: r for r in db.rows(
        f"SELECT line_id, SUM(amount) AS spent, COUNT(*) AS n, MAX(day) AS last_day FROM expenses e {cond} "
        f"GROUP BY line_id", params)}
    out = []
    for ln in lines():
        s = spent.get(ln["id"], {})
        ln["spent"] = round(s.get("spent") or 0, 2)
        ln["entries"] = s.get("n") or 0
        ln["last_day"] = s.get("last_day")
        ln["balance"] = round(ln["budget"] - ln["spent"], 2)
        ln["pct"] = (ln["spent"] / ln["budget"] * 100) if ln["budget"] else 0
        out.append(ln)
    return out


def expenses(start: date | None = None, end: date | None = None, line_id: int | None = None) -> list[dict]:
    where, params = [], []
    if start:
        where.append("e.day >= ?")
        params.append(d(start))
    if end:
        where.append("e.day <= ?")
        params.append(d(end))
    if line_id:
        where.append("e.line_id = ?")
        params.append(line_id)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    return db.rows(
        f"SELECT e.*, b.code, b.description AS line_name, b.category FROM expenses e "
        f"JOIN budget_lines b ON b.id = e.line_id {w} ORDER BY e.day, e.id", tuple(params))


def add_expense(day, line_id: int, description: str, payee: str, voucher: str, method: str,
                amount: float, by: str, demo: bool = False) -> int:
    return db.execute(
        "INSERT INTO expenses(day, line_id, description, payee, voucher, method, amount, entered_by, entered_at, demo) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (d(day), line_id, description.strip(), payee.strip(), voucher.strip(), method, round(float(amount), 2),
         by, now_iso(), int(demo)))


def delete_expense(eid: int) -> None:
    db.execute("DELETE FROM expenses WHERE id=?", (eid,))


def invoices() -> list[dict]:
    return db.rows("SELECT * FROM invoices ORDER BY sent_on, id")


def add_invoice(number, kind, sent_on, period_from, period_to, amount, status, note, by, demo=False) -> int:
    return db.execute(
        "INSERT INTO invoices(number, kind, sent_on, period_from, period_to, amount, status, note, entered_by, "
        "entered_at, demo) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (number.strip(), kind, d(sent_on), d(period_from), d(period_to), round(float(amount), 2), status,
         note.strip(), by, now_iso(), int(demo)))


def set_invoice_status(iid: int, status: str) -> None:
    db.execute("UPDATE invoices SET status=? WHERE id=?", (status, iid))


def delete_invoice(iid: int) -> None:
    db.execute("DELETE FROM invoices WHERE id=?", (iid,))


def instalments() -> list[dict]:
    return db.rows("SELECT i.*, v.number AS invoice_number FROM instalments i "
                   "LEFT JOIN invoices v ON v.id = i.invoice_id ORDER BY received_on, i.id")


def add_instalment(label, received_on, amount, credited, invoice_id, reference, note, by, demo=False) -> int:
    return db.execute(
        "INSERT INTO instalments(label, received_on, amount, credited, invoice_id, reference, note, entered_by, "
        "entered_at, demo) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (label.strip(), d(received_on), round(float(amount), 2),
         round(float(credited), 2) if credited not in (None, "") else None, invoice_id, reference.strip(),
         note.strip(), by, now_iso(), int(demo)))


def delete_instalment(iid: int) -> None:
    db.execute("DELETE FROM instalments WHERE id=?", (iid,))


def totals() -> dict:
    s = db.settings()
    budget = db.scalar("SELECT COALESCE(SUM(budget),0) FROM budget_lines") or 0
    budget_alt = db.scalar("SELECT COALESCE(SUM(budget_alt),0) FROM budget_lines") or 0
    spent = db.scalar("SELECT COALESCE(SUM(amount),0) FROM expenses") or 0
    invoiced = db.scalar("SELECT COALESCE(SUM(amount),0) FROM invoices WHERE kind <> 'Financial report'") or 0
    received = db.scalar("SELECT COALESCE(SUM(amount),0) FROM instalments") or 0
    credited = db.scalar("SELECT COALESCE(SUM(credited),0) FROM instalments") or 0
    uncredited = db.scalar("SELECT COUNT(*) FROM instalments WHERE credited IS NULL") or 0
    return {
        "currency": s["currency"], "alt": s["alt_currency"], "rate": rate(),
        "budget": budget, "budget_alt": budget_alt, "spent": spent, "balance": budget - spent,
        "burn": (spent / budget * 100) if budget else 0,
        "invoiced": invoiced, "received": received, "outstanding": invoiced - received,
        "credited": credited, "uncredited": uncredited, "cash": credited - spent,
        "n_invoices": db.scalar("SELECT COUNT(*) FROM invoices") or 0,
        "n_instalments": db.scalar("SELECT COUNT(*) FROM instalments") or 0,
        "demo_rows": (db.scalar("SELECT (SELECT COUNT(*) FROM expenses WHERE demo=1) + "
                                "(SELECT COUNT(*) FROM invoices WHERE demo=1) + "
                                "(SELECT COUNT(*) FROM instalments WHERE demo=1)") or 0),
    }


def monthly_spending() -> list[dict]:
    return db.rows("SELECT substr(day,1,7) AS month, SUM(amount) AS amount, COUNT(*) AS n FROM expenses "
                   "GROUP BY month ORDER BY month")


def clear_demo() -> int:
    n = 0
    with db.connect(write=True) as con:
        for t in ("instalments", "invoices", "expenses"):
            n += con.execute(f"DELETE FROM {t} WHERE demo = 1").rowcount
    return n
