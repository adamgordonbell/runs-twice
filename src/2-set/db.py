"""Setup and stand-ins, the same in every stage. SQLite stands in for Postgres.

likes.db is the app's database: videos and reactions. The seeded video has 1204
likes, stored as 1204 reaction rows so the count can be SET from them.
notifications.db is the notification service, a separate system with its own
storage, so the app can't share a transaction with it. Both live in .data/<stage>/.
"""

import os
import sqlite3
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


def connect(path: Path | None = None) -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path or DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")  # a server and workers share the file
    conn.executescript(SCHEMA)
    return conn


def reset() -> None:
    """Fresh databases at 1204 likes."""
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


def has_liked(conn: sqlite3.Connection, user: str, video: str = VIDEO) -> bool:
    row = conn.execute("SELECT reaction FROM reactions WHERE user = ? AND video = ?", (user, video)).fetchone()
    return row is not None and row[0] == "LIKE"


def send_notification(video: str, user: str, idempotency_key: str | None = None) -> bool:
    """Stands in for an email or push provider. With a key, a repeat of a key it has
    already seen is dropped, the way payment and email APIs do. Returns True if this
    call actually sent something."""
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
