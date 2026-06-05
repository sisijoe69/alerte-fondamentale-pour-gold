"""SQLite persistence: subscribers, reports history, alerts log, macro snapshots."""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscribers (
    user_id INTEGER PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    username TEXT,
    first_name TEXT,
    subscribed_at TEXT NOT NULL,
    is_admin INTEGER DEFAULT 0,
    receives_daily INTEGER DEFAULT 1,
    receives_alerts INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    bias TEXT,
    conviction TEXT,
    bull_count INTEGER,
    bear_count INTEGER,
    gold_price REAL,
    summary TEXT,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS alerts_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    kind TEXT,
    payload TEXT
);

CREATE TABLE IF NOT EXISTS macro_snapshots (
    series_id TEXT NOT NULL,
    observation_date TEXT NOT NULL,
    value REAL,
    fetched_at TEXT NOT NULL,
    notified INTEGER DEFAULT 0,
    PRIMARY KEY(series_id, observation_date)
);

CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_created  ON alerts_log(created_at DESC);
"""


@dataclass
class Subscriber:
    user_id: int
    chat_id: int
    username: str | None
    first_name: str | None
    subscribed_at: str
    is_admin: bool
    receives_daily: bool
    receives_alerts: bool


@dataclass
class ReportRecord:
    id: int
    created_at: str
    bias: str
    conviction: str
    bull_count: int
    bear_count: int
    gold_price: float | None
    summary: str


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, isolation_level=None, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # ── Subscribers ────────────────────────────────────────────

    def upsert_subscriber(
        self,
        user_id: int,
        chat_id: int,
        username: str | None,
        first_name: str | None,
        is_admin: bool = False,
    ) -> bool:
        """Insert or update a subscriber. Returns True if it's a new row."""
        with self.connect() as conn:
            cur = conn.execute("SELECT user_id FROM subscribers WHERE user_id=?", (user_id,))
            existed = cur.fetchone() is not None
            now = datetime.utcnow().isoformat(timespec="seconds")
            if existed:
                conn.execute(
                    """UPDATE subscribers
                       SET chat_id=?, username=?, first_name=?,
                           is_admin=CASE WHEN ?=1 THEN 1 ELSE is_admin END
                       WHERE user_id=?""",
                    (chat_id, username, first_name, 1 if is_admin else 0, user_id),
                )
            else:
                conn.execute(
                    """INSERT INTO subscribers
                       (user_id, chat_id, username, first_name, subscribed_at, is_admin)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (user_id, chat_id, username, first_name, now, 1 if is_admin else 0),
                )
            return not existed

    def remove_subscriber(self, user_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM subscribers WHERE user_id=?", (user_id,))
            return cur.rowcount > 0

    def get_subscriber(self, user_id: int) -> Subscriber | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM subscribers WHERE user_id=?", (user_id,)).fetchone()
        return _to_subscriber(row) if row else None

    def list_subscribers(
        self, *, only_daily: bool = False, only_alerts: bool = False
    ) -> list[Subscriber]:
        sql = "SELECT * FROM subscribers WHERE 1=1"
        if only_daily:
            sql += " AND receives_daily=1"
        if only_alerts:
            sql += " AND receives_alerts=1"
        sql += " ORDER BY subscribed_at ASC"
        with self.connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [_to_subscriber(r) for r in rows]

    def set_pref(self, user_id: int, *, daily: bool | None = None, alerts: bool | None = None) -> None:
        sets: list[str] = []
        params: list = []
        if daily is not None:
            sets.append("receives_daily=?")
            params.append(1 if daily else 0)
        if alerts is not None:
            sets.append("receives_alerts=?")
            params.append(1 if alerts else 0)
        if not sets:
            return
        params.append(user_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE subscribers SET {', '.join(sets)} WHERE user_id=?", params)

    # ── Reports ───────────────────────────────────────────────

    def save_report(
        self,
        bias: str,
        conviction: str,
        bull_count: int,
        bear_count: int,
        gold_price: float | None,
        summary: str,
        raw: dict | None = None,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """INSERT INTO reports
                   (created_at, bias, conviction, bull_count, bear_count, gold_price, summary, raw_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.utcnow().isoformat(timespec="seconds"),
                    bias,
                    conviction,
                    bull_count,
                    bear_count,
                    gold_price,
                    summary[:2000],
                    json.dumps(raw, default=str) if raw else None,
                ),
            )
            return cur.lastrowid or 0

    def last_reports(self, limit: int = 5) -> list[ReportRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT id, created_at, bias, conviction, bull_count, bear_count,
                          gold_price, summary
                   FROM reports
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            ReportRecord(
                id=r["id"],
                created_at=r["created_at"],
                bias=r["bias"],
                conviction=r["conviction"],
                bull_count=r["bull_count"],
                bear_count=r["bear_count"],
                gold_price=r["gold_price"],
                summary=r["summary"],
            )
            for r in rows
        ]

    # ── Alerts log ────────────────────────────────────────────

    def log_alert(self, kind: str, payload: dict) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO alerts_log (created_at, kind, payload) VALUES (?, ?, ?)",
                (
                    datetime.utcnow().isoformat(timespec="seconds"),
                    kind,
                    json.dumps(payload, default=str),
                ),
            )

    # ── Macro snapshots (for alerts deduplication) ─────────────

    def macro_known(self, series_id: str, observation_date: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM macro_snapshots WHERE series_id=? AND observation_date=?",
                (series_id, observation_date),
            ).fetchone()
        return row is not None

    def macro_remember(self, series_id: str, observation_date: str, value: float | None) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO macro_snapshots
                   (series_id, observation_date, value, fetched_at, notified)
                   VALUES (?, ?, ?, ?, 1)""",
                (
                    series_id,
                    observation_date,
                    value,
                    datetime.utcnow().isoformat(timespec="seconds"),
                ),
            )

    def macro_last_value(self, series_id: str) -> tuple[str, float] | None:
        with self.connect() as conn:
            row = conn.execute(
                """SELECT observation_date, value FROM macro_snapshots
                   WHERE series_id=? AND value IS NOT NULL
                   ORDER BY observation_date DESC LIMIT 1""",
                (series_id,),
            ).fetchone()
        if not row:
            return None
        return (row["observation_date"], row["value"])


def _to_subscriber(row: sqlite3.Row) -> Subscriber:
    return Subscriber(
        user_id=row["user_id"],
        chat_id=row["chat_id"],
        username=row["username"],
        first_name=row["first_name"],
        subscribed_at=row["subscribed_at"],
        is_admin=bool(row["is_admin"]),
        receives_daily=bool(row["receives_daily"]),
        receives_alerts=bool(row["receives_alerts"]),
    )
