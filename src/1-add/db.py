"""Setup and stand-ins, the same in every stage. SQLite stands in for Postgres.

- The app's database (likes.db): videos and reactions. A seeded video starts with
  1204 likes, stored as 1204 reaction rows, so the count can be SET from them.
- The notification service (notifications.db): a separate system with its own
  storage, so nothing the app does can share a transaction with it.

The operations each stage is about live in that stage's own files, not here.
"""

import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("LIKES_DB", "likes.db"))
NOTIFY_DB_PATH = Path(os.environ.get("NOTIFY_DB", "notifications.db"))
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
"""

NOTIFY_SCHEMA = """
CREATE TABLE IF NOT EXISTS notifications (
    id              INTEGER PRIMARY KEY,
    idempotency_key TEXT UNIQUE,  -- optional; NULLs never collide
    video           TEXT NOT NULL,
    message         TEXT NOT NULL
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")  # a server and workers share the file
    conn.executescript(SCHEMA)
    return conn


def reset() -> None:
    for path in (DB_PATH, NOTIFY_DB_PATH):
        for suffix in ("", "-wal", "-shm"):
            Path(f"{path}{suffix}").unlink(missing_ok=True)
    with connect() as conn:
        conn.execute("INSERT INTO videos VALUES (?, ?)", (VIDEO, SEED_LIKES))
        conn.executemany(
            "INSERT INTO reactions VALUES (?, ?, 'LIKE')",
            [(f"viewer-{i:04d}", VIDEO) for i in range(SEED_LIKES)],
        )


def like_count(conn: sqlite3.Connection, video: str = VIDEO) -> int:
    return conn.execute("SELECT like_count FROM videos WHERE id = ?", (video,)).fetchone()[0]


def send_notification(video: str, user: str, idempotency_key: str | None = None) -> bool:
    """The notification service. Stands in for an email or push provider.

    Without a key, every call sends. With a key, the service drops a repeat of a
    key it has already seen, the way payment and email APIs do. Returns True if
    this call sent a notification.
    """
    service = sqlite3.connect(NOTIFY_DB_PATH, timeout=10)
    service.executescript(NOTIFY_SCHEMA)
    with service:
        cur = service.execute(
            "INSERT INTO notifications (idempotency_key, video, message) VALUES (?, ?, ?) "
            "ON CONFLICT (idempotency_key) DO NOTHING",
            (idempotency_key, video, f"{user} liked your video"),
        )
    service.close()
    return cur.rowcount == 1


def notifications(video: str = VIDEO) -> list[str]:
    service = sqlite3.connect(NOTIFY_DB_PATH, timeout=10)
    service.executescript(NOTIFY_SCHEMA)
    rows = service.execute("SELECT message FROM notifications WHERE video = ? ORDER BY id", (video,)).fetchall()
    service.close()
    return [message for (message,) in rows]
