"""Stage 2: the like causes more work, made safe to retry by hand.

The request handler stores the reaction and an event with a stable ID in one
transaction. A worker then updates the like count and notifies the creator, and
has to remember which of those steps it already finished.

    uv run hand_rolled.py                          # like, then process
    CRASH_AT=after-notify uv run hand_rolled.py    # dies between two steps
    uv run hand_rolled.py --process                # rerun: resumes, no repeats
"""

import sqlite3
import sys

import chaos
import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS like_events (
    event_id TEXT PRIMARY KEY,
    user     TEXT NOT NULL,
    video    TEXT NOT NULL,
    done     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS steps_done (
    event_id TEXT NOT NULL,
    step     TEXT NOT NULL,
    PRIMARY KEY (event_id, step)
);
"""


def handle_like(conn: sqlite3.Connection, user: str, video: str) -> None:
    """Request handler. The event ID comes from the like itself, so a retried request finds the same event."""
    event_id = f"like-{user}-{video}"
    with conn:
        conn.execute(
            "INSERT INTO reactions VALUES (?, ?, 'LIKE') "
            "ON CONFLICT (user, video) DO UPDATE SET reaction = 'LIKE'",
            (user, video),
        )
        conn.execute(
            "INSERT INTO like_events (event_id, user, video) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
            (event_id, user, video),
        )


def step_done(conn: sqlite3.Connection, event_id: str, step: str) -> bool:
    row = conn.execute("SELECT 1 FROM steps_done WHERE event_id = ? AND step = ?", (event_id, step))
    return row.fetchone() is not None


def mark_done(conn: sqlite3.Connection, event_id: str, step: str) -> None:
    conn.execute("INSERT INTO steps_done VALUES (?, ?)", (event_id, step))


def process(conn: sqlite3.Connection, event_id: str, user: str, video: str) -> None:
    if not step_done(conn, event_id, "count"):
        with conn:  # the count and its checkmark commit together, so they can't disagree
            conn.execute(
                "UPDATE videos SET like_count = "
                "(SELECT COUNT(*) FROM reactions WHERE video = ? AND reaction = 'LIKE') WHERE id = ?",
                (video, video),
            )
            mark_done(conn, event_id, "count")
        count = db.like_count(conn, video)
        print(f"  count updated: {count}")

    if not step_done(conn, event_id, "notify"):
        # The notification service is outside our database, so this can't share the
        # transaction above. A crash after sending but before mark_done sends it again,
        # which is only safe because the service ignores a repeated event_id.
        sent = db.send_notification(event_id, video, user)
        chaos.crash_point("after-notify")
        with conn:
            mark_done(conn, event_id, "notify")
        print("  creator notified" if sent else "  notification was a repeat, service ignored it")

    with conn:
        conn.execute("UPDATE like_events SET done = 1 WHERE event_id = ?", (event_id,))


def run_worker(conn: sqlite3.Connection) -> None:
    # TODO: claim each event with a lease, so two workers don't process the same one
    # TODO: notice a worker that died holding a claim, and give its event to another
    # TODO: retry a failed step with backoff, and give up (and alert) eventually
    # TODO: time out a step that hangs, so it can't block the queue
    # TODO: a way to see which events are stuck, and why
    pending = conn.execute("SELECT event_id, user, video FROM like_events WHERE done = 0").fetchall()
    for event_id, user, video in pending:
        print(f"processing {event_id}")
        process(conn, event_id, user, video)


if __name__ == "__main__":
    if "--process" not in sys.argv:
        db.reset()
        chaos.clear()
    with db.connect() as conn:
        conn.executescript(SCHEMA)
        if "--process" not in sys.argv:
            print(f"{db.like_count(conn)} likes, Alice clicks once (and the client retries)")
            handle_like(conn, "alice", db.VIDEO)
            handle_like(conn, "alice", db.VIDEO)
        run_worker(conn)
        print(f"-> {db.like_count(conn)} likes, {db.notification_count(conn)} notification(s)")
