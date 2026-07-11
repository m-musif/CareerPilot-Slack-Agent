"""
Per-user persistent memory for CareerPilot (SQLite).
Each Slack user gets an isolated conversation history.
"""
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "careerpilot_memory.db"
_lock = threading.Lock()

# Keep a rolling window of recent turns per user fed back to the LLM.
HISTORY_LIMIT = 12


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   TEXT NOT NULL,
            role      TEXT NOT NULL,
            content   TEXT NOT NULL,
            agent     TEXT,
            ts        REAL NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user ON messages(user_id, id)")
    return conn


def add_message(user_id: str, role: str, content: str, agent: str = "") -> None:
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO messages (user_id, role, content, agent, ts) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, role, content, agent, time.time()),
            )
            conn.commit()
        finally:
            conn.close()


def get_history(user_id: str, limit: int = HISTORY_LIMIT) -> list[dict]:
    """Return recent turns as chat messages (oldest first)."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE user_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        finally:
            conn.close()
    return [{"role": r, "content": c} for r, c in reversed(rows)]


def clear_history(user_id: str) -> int:
    with _lock:
        conn = _connect()
        try:
            cur = conn.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()


def stats(user_id: str) -> dict:
    with _lock:
        conn = _connect()
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE user_id = ?", (user_id,)
            ).fetchone()[0]
        finally:
            conn.close()
    return {"user_id": user_id, "messages": total}
