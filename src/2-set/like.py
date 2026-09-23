"""Stage 2: a like is state, so running it twice is safe.

The handler stores (alice, video-123) = LIKE and SETs the count from the
reactions. The retry finds the same row and computes the same count.
Run: uv run like.py
"""

import sqlite3

import db


def handle_like(conn: sqlite3.Connection, user: str, video: str) -> None:
    """A like is state: (user, video) = LIKE. The count follows from the reactions."""
    with conn:
        conn.execute(
            "INSERT INTO reactions VALUES (?, ?, 'LIKE') "
            "ON CONFLICT (user, video) DO UPDATE SET reaction = 'LIKE'",
            (user, video),
        )
        conn.execute(
            "UPDATE videos SET like_count = "
            "(SELECT COUNT(*) FROM reactions WHERE video = ? AND reaction = 'LIKE') WHERE id = ?",
            (video, video),
        )


def click_like(conn: sqlite3.Connection) -> None:
    """The client. The first response never arrives, so it sends the same request again."""
    handle_like(conn, "alice", db.VIDEO)
    print("  response lost, client retries")
    handle_like(conn, "alice", db.VIDEO)


if __name__ == "__main__":
    db.reset()
    with db.connect() as conn:
        print(f"{db.like_count(conn)} likes, Alice clicks once")
        click_like(conn)
        print(f"-> {db.like_count(conn)} likes")
