"""The app's database. SQLite stands in for Postgres.

A seeded video starts with 1204 likes, stored as 1204 reaction rows, so the like
count can always be recomputed from the reactions rather than incremented.
"""

import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("LIKES_DB", "likes.db"))
VIDEO = "video-123"
SEED_LIKES = 1204

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id         TEXT PRIMARY KEY,
    like_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS reactions (
    user     TEXT NOT NULL,
    video    TEXT NOT NULL,
    reaction TEXT NOT NULL,
    PRIMARY KEY (user, video)
);
-- Stands in for an external notification service that accepts an idempotency key.
CREATE TABLE IF NOT EXISTS notifications (
    event_id TEXT PRIMARY KEY,
    video    TEXT NOT NULL,
    message  TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def reset() -> None:
    DB_PATH.unlink(missing_ok=True)
    with connect() as conn:
        conn.execute("INSERT INTO videos VALUES (?, ?)", (VIDEO, SEED_LIKES))
        conn.executemany(
            "INSERT INTO reactions VALUES (?, ?, 'LIKE')",
            [(f"viewer-{i:04d}", VIDEO) for i in range(SEED_LIKES)],
        )


def like_count(conn: sqlite3.Connection, video: str = VIDEO) -> int:
    return conn.execute("SELECT like_count FROM videos WHERE id = ?", (video,)).fetchone()[0]


def set_reaction(conn: sqlite3.Connection, user: str, video: str, reaction: str = "LIKE") -> None:
    """Store the reaction as state. Doing this twice leaves the same row."""
    conn.execute(
        "INSERT INTO reactions VALUES (?, ?, ?) "
        "ON CONFLICT (user, video) DO UPDATE SET reaction = excluded.reaction",
        (user, video, reaction),
    )


def recompute_like_count(conn: sqlite3.Connection, video: str) -> int:
    """SET the count from the reactions. Doing this twice gives the same count."""
    conn.execute(
        "UPDATE videos SET like_count = "
        "(SELECT COUNT(*) FROM reactions WHERE video = ? AND reaction = 'LIKE') WHERE id = ?",
        (video, video),
    )
    return like_count(conn, video)


def send_notification(event_id: str, video: str, user: str) -> bool:
    """Notify the creator. The service drops a repeat of an event_id it has already seen.

    It is a separate system, so it gets its own connection and commits on its own,
    whatever happens to the caller's transaction afterwards. Returns True if this
    call delivered the notification, False if it was a repeat.
    """
    service = connect()
    with service:
        cur = service.execute(
            "INSERT INTO notifications VALUES (?, ?, ?) ON CONFLICT (event_id) DO NOTHING",
            (event_id, video, f"{user} liked your video"),
        )
    service.close()
    return cur.rowcount == 1


def notification_count(conn: sqlite3.Connection, video: str = VIDEO) -> int:
    return conn.execute("SELECT COUNT(*) FROM notifications WHERE video = ?", (video,)).fetchone()[0]
