"""The hand-rolled queue: tables a worker uses to claim a like, check off its steps, and finish it. Temporal replaces all of this."""

import sqlite3

import likes

CLAIM_TIMEOUT = 30  # seconds. Quiet this long and we assume the worker died.

SCHEMA = """
CREATE TABLE IF NOT EXISTS like_events (
    id    TEXT PRIMARY KEY,
    user  TEXT NOT NULL,
    video TEXT NOT NULL,
    done  INTEGER NOT NULL DEFAULT 0,
    claimed_at REAL  -- when a worker took it; NULL = nobody has
);
CREATE TABLE IF NOT EXISTS steps_done (
    event_id TEXT NOT NULL,
    step     TEXT NOT NULL,
    PRIMARY KEY (event_id, step)
);
"""


def connect() -> sqlite3.Connection:
    conn = likes.connect()
    conn.executescript(SCHEMA)
    return conn


def add(conn: sqlite3.Connection, event_id: str, user: str, video: str) -> None:
    """Note that a like needs finishing. A repeat of the same like changes nothing."""
    conn.execute(
        "INSERT INTO like_events (id, user, video) VALUES (?, ?, ?) ON CONFLICT (id) DO NOTHING",
        (event_id, user, video),
    )


def pending(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    return conn.execute("SELECT id, user, video FROM like_events WHERE done = 0").fetchall()


def claim(conn: sqlite3.Connection, event_id: str, now: float) -> bool:
    """Take the event if it's free or its worker has gone quiet. Quiet isn't dead, so a step can run twice."""
    with conn:
        taken = conn.execute(
            "UPDATE like_events SET claimed_at = ? "
            "WHERE id = ? AND done = 0 AND (claimed_at IS NULL OR claimed_at < ?)",
            (now, event_id, now - CLAIM_TIMEOUT),
        )
    return taken.rowcount == 1


def release(conn: sqlite3.Connection, event_id: str) -> None:
    conn.execute("UPDATE like_events SET claimed_at = NULL WHERE id = ?", (event_id,))


def step_done(conn: sqlite3.Connection, event_id: str, step: str) -> bool:
    row = conn.execute("SELECT 1 FROM steps_done WHERE event_id = ? AND step = ?", (event_id, step))
    return row.fetchone() is not None


def mark_done(conn: sqlite3.Connection, event_id: str, step: str) -> None:
    # ON CONFLICT: a slow worker may finish a step the one that took over already finished.
    conn.execute("INSERT INTO steps_done VALUES (?, ?) ON CONFLICT DO NOTHING", (event_id, step))


def finish(conn: sqlite3.Connection, event_id: str) -> None:
    conn.execute("UPDATE like_events SET done = 1 WHERE id = ?", (event_id,))
