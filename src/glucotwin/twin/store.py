"""SQLite store for the twin's own records.

Clinical data are read from the hospital feed (FHIR export + CGM) up to the
current time; this store keeps what the twin and the staff add on top:
versioned ward snapshots, dose decisions, extra checks, follow-up bookings and
an append-only audit log.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ..config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS clock (ward TEXT PRIMARY KEY, now TEXT);
CREATE TABLE IF NOT EXISTS snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, ward TEXT, as_of TEXT, model_version TEXT, board TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, admission_id TEXT, as_of TEXT, dose_kind TEXT,
    dose_time TEXT, ordered_units REAL, decision TEXT, units REAL, by TEXT, note TEXT, flags TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS checks (id INTEGER PRIMARY KEY AUTOINCREMENT, admission_id TEXT, as_of TEXT, check_time TEXT,
    reason TEXT, status TEXT, by TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS followups (id INTEGER PRIMARY KEY AUTOINCREMENT, admission_id TEXT, as_of TEXT, clinic TEXT,
    due TEXT, by TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, ward TEXT, admission_id TEXT, as_of TEXT, actor TEXT,
    event TEXT, detail TEXT, created TEXT);
"""


def _utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path | str = DB_PATH):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self._lock = threading.RLock()

    def _x(self, sql, args=()):
        with self._lock, self.conn:
            return self.conn.execute(sql, args)

    def _df(self, sql, args=()):
        return pd.read_sql_query(sql, self.conn, params=args)

    # clock
    def set_clock(self, ward: str, now: pd.Timestamp):
        self._x("REPLACE INTO clock VALUES (?,?)", (ward, now.isoformat()))

    def clock(self, ward: str):
        r = self.conn.execute("SELECT now FROM clock WHERE ward=?", (ward,)).fetchone()
        return pd.Timestamp(r[0]) if r else None

    # records
    def snapshot(self, ward, as_of, version, board: list[dict]) -> int:
        return self._x("INSERT INTO snapshots (ward, as_of, model_version, board, created) VALUES (?,?,?,?,?)",
                       (ward, as_of.isoformat(), version, json.dumps(board, default=str), _utc())).lastrowid

    def decision(self, aid, as_of, kind, dose_time, ordered, decision, units, by, note, flags):
        self._x("INSERT INTO decisions (admission_id, as_of, dose_kind, dose_time, ordered_units, decision, units, by, note, flags, created) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (aid, as_of.isoformat(), kind, str(dose_time), ordered, decision, units, by, note,
                                                   json.dumps(flags), _utc()))

    def add_check(self, aid, as_of, check_time, reason, by):
        self._x("INSERT INTO checks (admission_id, as_of, check_time, reason, status, by, created) VALUES (?,?,?,?,?,?,?)",
                (aid, as_of.isoformat(), str(check_time), reason, "scheduled", by, _utc()))

    def followup(self, aid, as_of, clinic, due, by):
        self._x("INSERT INTO followups (admission_id, as_of, clinic, due, by, created) VALUES (?,?,?,?,?,?)",
                (aid, as_of.isoformat(), clinic, str(due), by, _utc()))

    def audit(self, ward, aid, as_of, actor, event, detail: dict):
        self._x("INSERT INTO audit (ward, admission_id, as_of, actor, event, detail, created) VALUES (?,?,?,?,?,?,?)",
                (ward, aid, as_of.isoformat() if as_of is not None else None, actor, event, json.dumps(detail, default=str), _utc()))

    def table(self, name: str, aid: str | None = None, limit: int = 200) -> pd.DataFrame:
        if aid:
            return self._df(f"SELECT * FROM {name} WHERE admission_id=? ORDER BY id DESC LIMIT ?", (aid, limit))
        return self._df(f"SELECT * FROM {name} ORDER BY id DESC LIMIT ?", (limit,))

    def reset(self):
        with self._lock, self.conn:
            for t in ("clock", "snapshots", "decisions", "checks", "followups", "audit"):
                self.conn.execute(f"DELETE FROM {t}")
