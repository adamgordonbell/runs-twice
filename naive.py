"""Stage 1: what happens if this runs twice?

Alice clicks Like once. The server does the work, the response is lost, and the
client retries. Run: uv run naive.py
"""

import sqlite3

import db


def like_add(conn: sqlite3.Connection, user: str, video: str) -> None:
    """The first handler: a like is +1."""
    with conn:
        conn.execute("UPDATE videos SET like_count = like_count + 1 WHERE id = ?", (video,))


def like_set(conn: sqlite3.Connection, user: str, video: str) -> None:
    """The fix: a like is state, (Alice, video-123) = LIKE, and the count follows from it."""
    with conn:
        db.set_reaction(conn, user, video)
        db.recompute_like_count(conn, video)


def click_like(handler, conn: sqlite3.Connection) -> None:
    """The client. The first response never arrives, so it sends the same request again."""
    handler(conn, "alice", db.VIDEO)
    print("  response lost, client retries")
    handler(conn, "alice", db.VIDEO)


if __name__ == "__main__":
    for handler in (like_add, like_set):
        db.reset()
        with db.connect() as conn:
            print(f"{handler.__name__}: {db.like_count(conn)} likes, Alice clicks once")
            click_like(handler, conn)
            print(f"  -> {db.like_count(conn)} likes\n")
