"""The outbox: notes saved in the same transaction as the like, waiting for the relay to hand them to Temporal."""

import sqlite3

import likes

SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
    id      TEXT PRIMARY KEY,  -- the like's event ID: it becomes the workflow ID and the notification key
    user    TEXT NOT NULL,
    video   TEXT NOT NULL,
    sent_at REAL               -- when the relay handed it to Temporal; NULL = not yet
);
"""


def connect() -> sqlite3.Connection:
    conn = likes.connect()
    conn.executescript(SCHEMA)
    return conn


def add(conn: sqlite3.Connection, event_id: str, user: str, video: str) -> None:
    """Note that a like needs telling Temporal about. A repeat of the same like changes nothing."""
    conn.execute(
        "INSERT INTO outbox (id, user, video) VALUES (?, ?, ?) ON CONFLICT (id) DO NOTHING",
        (event_id, user, video),
    )


def unsent(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    return conn.execute("SELECT id, user, video FROM outbox WHERE sent_at IS NULL").fetchall()


def mark_sent(conn: sqlite3.Connection, event_id: str, now: float) -> None:
    conn.execute("UPDATE outbox SET sent_at = ? WHERE id = ?", (now, event_id))
