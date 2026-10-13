"""Starting data for a new database, and optional demo financial entries for presentations."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from core import acts, db, money

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
PLAIN_FILE = SEED_DIR / "project.json"
LOCKED_FILE = SEED_DIR / "project.enc"


class SeedLocked(Exception):
    """The starting data is encrypted and the key (SEED_KEY) is missing or wrong."""


def read_seed() -> dict:
    """The starting data: the plain file if present, otherwise the encrypted one, unlocked with SEED_KEY.

    In a public repository only the encrypted file is published, so the budget and staff list
    stay private. The key is kept in the app's secrets.
    """
    if PLAIN_FILE.exists():
        return json.loads(PLAIN_FILE.read_text(encoding="utf-8"))
    if not LOCKED_FILE.exists():
        raise SeedLocked("No starting data file was found.")
    key = db._secret("SEED_KEY").strip()
    if not key:
        raise SeedLocked("The starting data is locked. Add SEED_KEY to the app's secrets.")
    import base64
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        raw = base64.b64decode(LOCKED_FILE.read_text().strip())
        plain = AESGCM(base64.urlsafe_b64decode(key)).decrypt(raw[:12], raw[12:], None)
    except Exception as exc:
        raise SeedLocked("SEED_KEY does not unlock the starting data. Check that it was copied exactly.") from exc
    return json.loads(plain.decode("utf-8"))


def load_project(data: dict | None = None) -> None:
    """Fill an empty database with the project's settings, people, activities and budget."""
    data = data or read_seed()
    db.save_settings(data["settings"])
    ids = {}
    for p in data["people"]:
        ids[p["name"]] = db.save_person(None, p["name"], p.get("email", ""), p.get("title", ""), p["role"])
    with db.connect(write=True) as con:
        con.executemany(
            "INSERT INTO budget_lines(code, donor_line, category, description, units, budget, budget_alt, sort) "
            "VALUES (?,?,?,?,?,?,?,?)",
            [(b["code"], b["donor_line"], b["category"], b["description"], b["units"], b["budget"],
              b["budget_alt"], b["sort"]) for b in data["budget_lines"]])
    for a in data["activities"]:
        acts.save({
            "ref": a["ref"], "title": a["title"], "description": a["description"], "kind": a["kind"],
            "recurring": a.get("recurring", False), "frequency": a.get("frequency"),
            "days": a.get("days", []), "start_date": a.get("start_date"), "end_date": a.get("end_date"),
            "lead_id": ids.get(a.get("lead_name")), "support_ids": [ids[n] for n in a.get("support_names", []) if n in ids],
            "priority": "High" if a.get("key") else "Normal", "location": a.get("location", ""),
            "workplan_ref": a.get("workplan_ref", ""), "key_activity": a.get("key", False),
            "log_note": "Imported from the project workplan",
        }, by="Workplan import")


def load_demo_finance(by: str) -> int:
    """Sample entries, all labelled [Demo], so the finance pages can be shown before real data exists.
    They are removed with money.clear_demo()."""
    lines = {ln["code"]: ln["id"] for ln in money.lines()}
    s = db.settings()
    start = date.fromisoformat(s["start_date"]) if s["start_date"] else date.today().replace(day=1)
    today = date.today()
    sample = [
        (0, "II.2.1", "Kabul coordination office rent, 20% share, October", "Office landlord", "Bank transfer", 400),
        (1, "II.2.7", "Vehicle rental, Dare Suf, October", "Transport contractor", "Bank transfer", 1000),
        (1, "II.2.8", "Vehicle rental, Ruyduab, October", "Transport contractor", "Bank transfer", 1000),
        (1, "II.2.9", "Vehicle rental, Maidan Shahr, October", "Transport contractor", "Bank transfer", 1000),
        (2, "II.3.2", "Laptops for core staff (6)", "IT supplier", "Bank transfer", 3000),
        (2, "II.3.4", "Printers (2)", "IT supplier", "Bank transfer", 900),
        (4, "II.2.3", "Office furniture, three field offices", "Furniture supplier", "Bank transfer", 1450),
        (5, "II.2.2", "Office supplies, three field offices, October", "Stationery shop", "Cash", 310),
        (6, "II.2.5", "Mobile top-up cards, Samangan and Wardak, October", "Telecom agent", "Cash", 300),
        (7, "II.3.5", "Tablets for case workers (18)", "IT supplier", "Bank transfer", 1980),
        (8, "II.6.1", "Banners and visibility material", "Printing house", "Cash", 380),
        (9, "II.1.5", "Local transport for support staff, October", "Taxi service", "Cash", 120),
    ]
    n = 0
    for offset, code, desc, payee, method, amount in sample:
        day = min(start + timedelta(days=offset), today)
        if code in lines:
            money.add_expense(day, lines[code], f"[Demo] {desc}", payee, f"DEMO-{n + 1:03d}", method, amount, by, demo=True)
            n += 1
    total_alt = db.scalar("SELECT COALESCE(SUM(budget_alt),0) FROM budget_lines") or 0
    pre = round(total_alt * 0.30, 2)
    inv = money.add_invoice("DEMO-FR-01", "Funds request", min(start + timedelta(days=2), today), start,
                            s["end_date"] or None, pre, "Paid",
                            "[Demo] Pre-financing request, 30% of the total budget, with full-period forecast", by, demo=True)
    money.add_instalment("[Demo] 1st instalment (pre-financing)", min(start + timedelta(days=10), today), pre,
                         round(pre * money.rate(), 2), inv, "DEMO-BANK-REF", "", by, demo=True)
    return n + 2
