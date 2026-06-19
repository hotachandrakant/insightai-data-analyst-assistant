"""SQLite persistence layer for InsightAI.

Stores a lightweight audit trail of uploaded datasets, chatbot queries and
generated reports. This gives the app a sense of "memory" across sessions and
demonstrates data-engineering practice (schema management, parameterised
queries, connection handling).
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from utils.config import load_config
from utils.logger import get_logger

logger = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    email           TEXT    NOT NULL UNIQUE,
    phone           TEXT,
    password_hash   TEXT    NOT NULL,
    email_verified  INTEGER NOT NULL DEFAULT 0,
    phone_verified  INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL,
    last_login      TEXT
);

CREATE TABLE IF NOT EXISTS datasets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    rows        INTEGER NOT NULL,
    columns     INTEGER NOT NULL,
    uploaded_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS queries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset     TEXT,
    question    TEXT    NOT NULL,
    answer      TEXT,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset     TEXT,
    report_type TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);
"""


class Database:
    """Thin wrapper around a SQLite connection with helper methods."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Context-managed connection with row factory and auto-commit."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            logger.exception("Database transaction failed")
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
        logger.info("Database schema ensured at %s", self.db_path)

    # ── Writes ─────────────────────────────────────────────────────────
    def log_dataset(self, name: str, rows: int, columns: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO datasets (name, rows, columns, uploaded_at) "
                "VALUES (?, ?, ?, ?)",
                (name, rows, columns, datetime.utcnow().isoformat(timespec="seconds")),
            )

    def log_query(self, dataset: str | None, question: str, answer: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO queries (dataset, question, answer, created_at) "
                "VALUES (?, ?, ?, ?)",
                (dataset, question, answer, datetime.utcnow().isoformat(timespec="seconds")),
            )

    def log_report(self, dataset: str | None, report_type: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO reports (dataset, report_type, created_at) "
                "VALUES (?, ?, ?)",
                (dataset, report_type, datetime.utcnow().isoformat(timespec="seconds")),
            )

    # ── Users / auth ───────────────────────────────────────────────────
    def create_user(self, name: str, email: str, phone: str, password_hash: str) -> int:
        """Insert a new (unverified) user. Returns the new user id."""
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO users (name, email, phone, password_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, email.lower(), phone, password_hash,
                 datetime.utcnow().isoformat(timespec="seconds")),
            )
            return int(cur.lastrowid)

    def get_user(self, email: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email.lower(),)
            ).fetchone()
        return dict(row) if row else None

    def email_exists(self, email: str) -> bool:
        return self.get_user(email) is not None

    def set_verified(self, email: str, field: str) -> None:
        """Mark ``email_verified`` or ``phone_verified`` for a user."""
        if field not in ("email_verified", "phone_verified"):
            raise ValueError(f"Invalid verification field: {field}")
        with self._connect() as conn:
            conn.execute(
                f"UPDATE users SET {field} = 1 WHERE email = ?", (email.lower(),)
            )

    def update_password(self, email: str, password_hash: str) -> None:
        """Replace a user's password hash (used by the reset flow)."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE email = ?",
                (password_hash, email.lower()),
            )

    def touch_login(self, email: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET last_login = ? WHERE email = ?",
                (datetime.utcnow().isoformat(timespec="seconds"), email.lower()),
            )

    # ── Reads ──────────────────────────────────────────────────────────
    def recent_datasets(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM datasets ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def recent_queries(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM queries ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict[str, int]:
        """Return high-level counts for the home dashboard."""
        with self._connect() as conn:
            datasets = conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
            queries = conn.execute("SELECT COUNT(*) FROM queries").fetchone()[0]
            reports = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        return {"datasets": datasets, "queries": queries, "reports": reports}


_db: Database | None = None


def get_database() -> Database:
    """Return a cached singleton :class:`Database`."""
    global _db
    if _db is None:
        _db = Database(load_config().db_path)
    return _db
