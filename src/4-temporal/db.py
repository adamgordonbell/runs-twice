"""The app's database (likes.db) and a stand-in notification service (notifications.db), in .data/<stage>/."""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / ".data" / Path(__file__).parent.name
DB_PATH = Path(os.environ.get("LIKES_DB", DATA_DIR / "likes.db"))
NOTIFY_DB_PATH = Path(os.environ.get("NOTIFY_DB", DATA_DIR / "notifications.db"))
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


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
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
    with _service() as service:
        service.executescript(NOTIFY_SCHEMA)


def like_count(conn: sqlite3.Connection, video: str = VIDEO) -> int:
    return conn.execute("SELECT like_count FROM videos WHERE id = ?", (video,)).fetchone()[0]


def has_liked(conn: sqlite3.Connection, user: str, video: str = VIDEO) -> bool:
    row = conn.execute("SELECT reaction FROM reactions WHERE user = ? AND video = ?", (user, video)).fetchone()
    return row is not None and row[0] == "LIKE"


@contextmanager
def _service() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(NOTIFY_DB_PATH, timeout=10)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def send_notification(video: str, user: str, idempotency_key: str | None = None) -> bool:
    """Returns False if this key was already sent, the way payment and email APIs drop a repeat."""
    with _service() as service:
        cur = service.execute(
            "INSERT INTO notifications (idempotency_key, video, message) VALUES (?, ?, ?) "
            "ON CONFLICT (idempotency_key) DO NOTHING",
            (idempotency_key, video, f"{user} liked your video"),
        )
    return cur.rowcount == 1


def notifications(video: str = VIDEO) -> list[str]:
    with _service() as service:
        rows = service.execute("SELECT message FROM notifications WHERE video = ? ORDER BY id", (video,)).fetchall()
    return [message for (message,) in rows]
