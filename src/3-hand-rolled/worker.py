"""Stage 3 worker: update the count, then notify the creator, for each new like.

Two lines of business logic, wrapped in the bookkeeping that makes them safe to
retry: a checkmark per finished step, so a rerun skips what's done.

    uv run worker.py
    FAIL_RATE=0.5 uv run worker.py    # steps fail at random; each pass skips what's done
"""

import os
import signal
import sqlite3
import time

import chaos
import db
from server import connect


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
        print(f"  count updated: {db.like_count(conn, video)}", flush=True)

    if not step_done(conn, event_id, "notify"):
        chaos.maybe_fail("before-notify")
        # The notification service is another system, so this can't share our transaction.
        # A crash after sending and before the checkmark sends again on the rerun, which is
        # only safe because the service drops a repeated idempotency key.
        sent = db.send_notification(video, user, idempotency_key=event_id)
        chaos.maybe_fail("after-notify")
        with conn:
            mark_done(conn, event_id, "notify")
        print("  creator notified" if sent else "  repeat notification, ignored", flush=True)

    with conn:
        conn.execute("UPDATE like_events SET done = 1 WHERE id = ?", (event_id,))


def run(conn: sqlite3.Connection) -> None:
    # TODO: two workers would grab the same event: needs leases
    # TODO: a worker that dies mid-event leaves it for whoever restarts: needs takeover
    # TODO: retry with backoff, and give up (and alert) eventually
    # TODO: time out a hung call, so it can't block the queue
    # TODO: a way to see what's stuck, and why
    while True:
        for event_id, user, video in conn.execute("SELECT id, user, video FROM like_events WHERE done = 0").fetchall():
            print(f"{event_id}", flush=True)
            try:
                process(conn, event_id, user, video)
            except Exception as error:  # noqa: BLE001 - left undone, tried again next pass
                print(f"  failed: {error!r}", flush=True)
        time.sleep(0.5)


if __name__ == "__main__":
    print(f"worker starting. FAIL_RATE={chaos.FAIL_RATE}", flush=True)
    # Ctrl-C kills the worker outright, like a crash, instead of shutting down cleanly.
    signal.signal(signal.SIGINT, lambda *_: os._exit(130))
    run(connect())
