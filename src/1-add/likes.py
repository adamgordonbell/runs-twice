"""The app's database: videos with their like count, and the reactions behind them. In .data/<stage>/likes.db."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parents[2] / ".data" / Path(__file__).parent.name / "likes.db"
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
-- Without this, counting a video's likes scans every reaction.
CREATE INDEX IF NOT EXISTS reactions_by_video ON reactions (video, reaction);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")  # a server and workers share the file
    conn.executescript(SCHEMA)
    return conn


def reset() -> None:
    for suffix in ("", "-wal", "-shm"):
        Path(f"{DB_PATH}{suffix}").unlink(missing_ok=True)
    with connect() as conn:
        conn.execute("INSERT INTO videos VALUES (?, ?)", (VIDEO, SEED_LIKES))
        conn.executemany(
            "INSERT INTO reactions VALUES (?, ?, 'LIKE')",
            [(f"viewer-{i:04d}", VIDEO) for i in range(SEED_LIKES)],
        )


def count(conn: sqlite3.Connection, video: str = VIDEO) -> int:
    return conn.execute("SELECT like_count FROM videos WHERE id = ?", (video,)).fetchone()[0]


def has_liked(conn: sqlite3.Connection, user: str, video: str = VIDEO) -> bool:
    row = conn.execute("SELECT reaction FROM reactions WHERE user = ? AND video = ?", (user, video)).fetchone()
    return row is not None and row[0] == "LIKE"


def increment(conn: sqlite3.Connection, video: str) -> None:
    """Add one to the count. Not safe to repeat: a retry counts the like twice."""
    conn.execute("UPDATE videos SET like_count = like_count + 1 WHERE id = ?", (video,))
