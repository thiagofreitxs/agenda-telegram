"""Persistência local em SQLite.

Guardamos:
- quais lembretes já foram enviados (para nunca avisar duas vezes);
- ajustes simples feitos pelo próprio bot (ex.: minutos de antecedência).
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from . import config

_lock = threading.Lock()
_connection: sqlite3.Connection | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sent_reminders (
    event_id   TEXT NOT NULL,
    start_iso  TEXT NOT NULL,
    sent_at    TEXT NOT NULL,
    PRIMARY KEY (event_id, start_iso)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    global _connection
    if _connection is None:
        directory = os.path.dirname(os.path.abspath(config.DATABASE_PATH))
        if directory:
            os.makedirs(directory, exist_ok=True)
        _connection = sqlite3.connect(config.DATABASE_PATH, check_same_thread=False)
        _connection.row_factory = sqlite3.Row
    return _connection


def init_db() -> None:
    with _lock:
        conn = _connect()
        conn.executescript(_SCHEMA)
        conn.commit()


# --- Lembretes já enviados ---------------------------------------------------
def reminder_already_sent(event_id: str, start_iso: str) -> bool:
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT 1 FROM sent_reminders WHERE event_id = ? AND start_iso = ?",
            (event_id, start_iso),
        ).fetchone()
        return row is not None


def mark_reminder_sent(event_id: str, start_iso: str) -> None:
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT OR REPLACE INTO sent_reminders (event_id, start_iso, sent_at) VALUES (?, ?, ?)",
            (event_id, start_iso, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def cleanup_old_reminders(days: int = 60) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _lock:
        conn = _connect()
        conn.execute("DELETE FROM sent_reminders WHERE sent_at < ?", (cutoff,))
        conn.commit()


# --- Ajustes ----------------------------------------------------------------
def get_setting(key: str, default: str | None = None) -> str | None:
    with _lock:
        conn = _connect()
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )
        conn.commit()
