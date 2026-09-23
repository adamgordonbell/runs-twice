"""Stage 1: what happens if this runs twice?

Alice clicks Like once. The server adds 1, the response is lost, and the client
retries. Run: uv run like.py
"""

import sqlite3

import db


def handle_like(conn: sqlite3.Connection, user: str, video: str) -> None:
    """A like is +1."""
    with conn:
        conn.execute("UPDATE videos SET like_count = like_count + 1 WHERE id = ?", (video,))


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
