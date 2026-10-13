"""Data layer: one SQLite file per project, with an optional backup to a private Hugging Face dataset.

Both Streamlit Community Cloud and Hugging Face erase the app's disk when it restarts. When
HF_TOKEN and DATA_REPO are set, the database is copied to that private dataset a few seconds
after every change and restored from it at start-up.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path


def _secret(name: str, default: str = "") -> str:
    """Read a setting from the environment, or from Streamlit secrets (Community Cloud)."""
    val = os.environ.get(name)
    if val:
        return val
    try:
        import streamlit as st
        return str(st.secrets.get(name, default))
    except Exception:
        return default


DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
DB_PATH = DATA_DIR / "tracker.db"
REMOTE_NAME = "tracker.db"
_write_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS people (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    email       TEXT,
    title       TEXT,
    role        TEXT NOT NULL DEFAULT 'team',     -- coordinator | finance | management | team
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activities (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ref           TEXT,
    title         TEXT NOT NULL,
    description   TEXT,
    kind          TEXT NOT NULL,                  -- one_time | selected_dates | date_range
    recurring     INTEGER NOT NULL DEFAULT 0,
    frequency     TEXT,                           -- weekly | monthly | quarterly
    start_date    TEXT,
    end_date      TEXT,
    lead_id       INTEGER REFERENCES people(id) ON DELETE SET NULL,
    priority      TEXT NOT NULL DEFAULT 'Normal',
    location      TEXT,
    workplan_ref  TEXT,
    flag          TEXT,                           -- NULL | blocked | cancelled
    progress      INTEGER NOT NULL DEFAULT 0,     -- used by date-range activities
    key_activity  INTEGER NOT NULL DEFAULT 0,     -- shown to management
    series_id     INTEGER,                        -- links recurring occurrences
    created_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activity_support (
    activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    person_id   INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    PRIMARY KEY (activity_id, person_id)
);

CREATE TABLE IF NOT EXISTS activity_dates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    day         TEXT NOT NULL,
    done        INTEGER NOT NULL DEFAULT 0,
    done_at     TEXT,
    done_by     TEXT,
    note        TEXT,
    UNIQUE (activity_id, day)
);

CREATE TABLE IF NOT EXISTS activity_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    at          TEXT NOT NULL,
    by_name     TEXT,
    kind        TEXT NOT NULL DEFAULT 'change',   -- change | note
    note        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budget_lines (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL,
    donor_line  TEXT,
    category    TEXT NOT NULL,
    description TEXT NOT NULL,
    units       TEXT,
    budget      REAL NOT NULL DEFAULT 0,          -- in the project currency
    budget_alt  REAL,                             -- in the agreement currency (reference)
    sort        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    day         TEXT NOT NULL,
    line_id     INTEGER NOT NULL REFERENCES budget_lines(id),
    description TEXT NOT NULL,
    payee       TEXT,
    voucher     TEXT,
    method      TEXT,
    amount      REAL NOT NULL,
    entered_by  TEXT,
    entered_at  TEXT NOT NULL,
    demo        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS invoices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    number      TEXT NOT NULL,
    kind        TEXT NOT NULL,                    -- Funds request | Invoice | Financial report
    sent_on     TEXT NOT NULL,
    period_from TEXT,
    period_to   TEXT,
    amount      REAL NOT NULL,                    -- agreement currency
    status      TEXT NOT NULL DEFAULT 'Sent',
    note        TEXT,
    entered_by  TEXT,
    entered_at  TEXT NOT NULL,
    demo        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS instalments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    label       TEXT NOT NULL,
    received_on TEXT NOT NULL,
    amount      REAL NOT NULL,                    -- agreement currency, as paid by the partner
    credited    REAL,                             -- project currency, as credited to the bank
    invoice_id  INTEGER REFERENCES invoices(id) ON DELETE SET NULL,
    reference   TEXT,
    note        TEXT,
    entered_by  TEXT,
    entered_at  TEXT NOT NULL,
    demo        INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_dates_act ON activity_dates(activity_id);
CREATE INDEX IF NOT EXISTS idx_dates_day ON activity_dates(day);
CREATE INDEX IF NOT EXISTS idx_exp_day ON expenses(day);
CREATE INDEX IF NOT EXISTS idx_exp_line ON expenses(line_id);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def d(v) -> str | None:
    """Normalise a date-like value to 'YYYY-MM-DD'."""
    if v is None or v == "":
        return None
    if isinstance(v, (date, datetime)):
        return v.isoformat()[:10]
    return str(v)[:10]


# --------------------------------------------------------------------------- backup
class RemoteBackup:
    def __init__(self) -> None:
        self.repo = _secret("DATA_REPO").strip()
        self.token = _secret("HF_TOKEN").strip()
        self.enabled = bool(self.repo and self.token)
        self._pending = False
        self._lock = threading.Lock()
        self.last_ok: str | None = None
        self.last_error: str | None = None
        self.restored = False

    def restore(self) -> None:
        if not self.enabled or DB_PATH.exists():
            return
        try:
            from huggingface_hub import hf_hub_download
            path = hf_hub_download(repo_id=self.repo, repo_type="dataset", filename=REMOTE_NAME,
                                   token=self.token, force_download=True)
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy(path, DB_PATH)
            self.restored = True
            self.last_ok = now_iso()
        except Exception as exc:
            self.last_error = f"Nothing restored ({exc.__class__.__name__}). Normal on the very first start."

    def schedule(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            if self._pending:
                return
            self._pending = True
        threading.Thread(target=self._push_later, daemon=True).start()

    def _push_later(self) -> None:
        time.sleep(3)
        with self._lock:
            self._pending = False
        try:
            from huggingface_hub import HfApi
            snap = DATA_DIR / "tracker.snapshot.db"
            with _write_lock:
                src, dst = sqlite3.connect(DB_PATH), sqlite3.connect(snap)
                src.backup(dst)
                src.close()
                dst.close()
            HfApi(token=self.token).upload_file(
                path_or_fileobj=str(snap), path_in_repo=REMOTE_NAME, repo_id=self.repo,
                repo_type="dataset", commit_message=f"Backup {now_iso()}")
            self.last_ok, self.last_error = now_iso(), None
        except Exception as exc:
            self.last_error = f"{exc.__class__.__name__}: {exc}"[:300]


backup = RemoteBackup()


# --------------------------------------------------------------------------- connection
def init() -> bool:
    """Create tables. Returns True when the database is brand new (empty)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    backup.restore()
    with connect() as con:
        con.executescript(SCHEMA)
        empty = con.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0
    return empty


@contextmanager
def connect(write: bool = False):
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        if write:
            with _write_lock:
                yield con
                con.commit()
        else:
            yield con
    finally:
        con.close()
    if write:
        backup.schedule()


def rows(sql: str, params: tuple = ()) -> list[dict]:
    with connect() as con:
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def one(sql: str, params: tuple = ()) -> dict | None:
    r = rows(sql, params)
    return r[0] if r else None


def scalar(sql: str, params: tuple = ()):
    with connect() as con:
        r = con.execute(sql, params).fetchone()
    return r[0] if r else None


def execute(sql: str, params: tuple = ()) -> int:
    with connect(write=True) as con:
        cur = con.execute(sql, params)
        return cur.lastrowid


# --------------------------------------------------------------------------- settings
SETTING_DEFAULTS = {
    "project_name": "New project",
    "project_code": "",
    "donor": "",
    "partner": "",
    "start_date": "",
    "end_date": "",
    "currency": "USD",            # ledger and budget currency
    "alt_currency": "EUR",        # agreement currency
    "alt_rate": "1.11",           # 1 alt = rate x currency
    "locations": "",
}


def settings() -> dict:
    vals = dict(SETTING_DEFAULTS)
    vals.update({r["key"]: r["value"] for r in rows("SELECT key, value FROM settings")})
    return vals


def save_settings(values: dict) -> None:
    with connect(write=True) as con:
        con.executemany("INSERT INTO settings(key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        [(k, "" if v is None else str(v)) for k, v in values.items()])


# --------------------------------------------------------------------------- people
ROLES = {
    "coordinator": "Project coordinator",
    "finance": "Finance focal point",
    "management": "Management",
    "team": "Team member",
}


def people(active_only: bool = True) -> list[dict]:
    where = "WHERE active = 1" if active_only else ""
    return rows(f"SELECT * FROM people {where} ORDER BY name COLLATE NOCASE")


def person(pid: int | None) -> dict | None:
    return one("SELECT * FROM people WHERE id = ?", (pid,)) if pid else None


def person_by_email(email: str) -> dict | None:
    return one("SELECT * FROM people WHERE lower(email) = lower(?) AND active = 1", (email.strip(),))


def save_person(pid: int | None, name: str, email: str, title: str, role: str, active: bool = True) -> int:
    email = (email or "").strip().lower() or None
    with connect(write=True) as con:
        if pid:
            con.execute("UPDATE people SET name=?, email=?, title=?, role=?, active=? WHERE id=?",
                        (name.strip(), email, title.strip(), role, int(active), pid))
            return pid
        cur = con.execute("INSERT INTO people(name, email, title, role, active, created_at) VALUES (?,?,?,?,?,?)",
                          (name.strip(), email, title.strip(), role, int(active), now_iso()))
        return cur.lastrowid
