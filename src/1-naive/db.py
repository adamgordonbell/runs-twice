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
