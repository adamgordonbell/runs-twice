"""A stand-in for the notification service: another system, with its own database. In .data/<stage>/notifications.db."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parents[2] / ".data" / Path(__file__).parent.name / "notifications.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS notifications (
    id      INTEGER PRIMARY KEY,
    video   TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS notifications_by_video ON notifications (video);
"""


def reset() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        Path(f"{DB_PATH}{suffix}").unlink(missing_ok=True)
    with _service() as service:
        service.executescript(SCHEMA)


@contextmanager
def _service() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def send(video: str, user: str) -> None:
    with _service() as service:
        service.execute(
            "INSERT INTO notifications (video, message) VALUES (?, ?)",
            (video, f"{user} liked your video"),
        )


def sent(video: str) -> list[str]:
    with _service() as service:
        rows = service.execute("SELECT message FROM notifications WHERE video = ? ORDER BY id", (video,)).fetchall()
    return [message for (message,) in rows]
