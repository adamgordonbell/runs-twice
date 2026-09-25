"""Stage 3 worker: update the count, then notify the creator, for each new like.

    uv run worker.py
    uv run worker.py                  # a second one, in another terminal; they share the events
    FAIL_RATE=0.5 uv run worker.py    # steps fail at random; each pass skips what's done
"""

import os
import signal
import sqlite3
import time

import chaos
import db
from server import connect


CLAIM_TIMEOUT = 30  # seconds. Quiet this long and we assume the worker died.


def claim(conn: sqlite3.Connection, event_id: str, now: float) -> bool:
    """Take the event if nobody has it, or if whoever had it has gone quiet.

    Quiet isn't the same as dead: if the old worker was only slow, it is still
    running this event too. So every step below has to be safe to run twice.
    """
    with conn:
        taken = conn.execute(
            "UPDATE like_events SET claimed_at = ? "
            "WHERE id = ? AND done = 0 AND (claimed_at IS NULL OR claimed_at < ?)",
            (now, event_id, now - CLAIM_TIMEOUT),
        )
    return taken.rowcount == 1


def step_done(conn: sqlite3.Connection, event_id: str, step: str) -> bool:
    row = conn.execute("SELECT 1 FROM steps_done WHERE event_id = ? AND step = ?", (event_id, step))
    return row.fetchone() is not None


def mark_done(conn: sqlite3.Connection, event_id: str, step: str) -> None:
    # ON CONFLICT: a slow worker may finish a step the one that took over already finished.
    conn.execute("INSERT INTO steps_done VALUES (?, ?) ON CONFLICT DO NOTHING", (event_id, step))


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
        # Another system, so it can't share our transaction. A crash between sending and
        # the checkmark sends again on the rerun; safe only because the service drops a repeated key.
        sent = db.send_notification(video, user, idempotency_key=event_id)
        chaos.maybe_fail("after-notify")
        with conn:
            mark_done(conn, event_id, "notify")
        print("  creator notified" if sent else "  repeat notification, ignored", flush=True)

    with conn:
        conn.execute("UPDATE like_events SET done = 1 WHERE id = ?", (event_id,))


def run(conn: sqlite3.Connection) -> None:
    # TODO: retry with backoff, and give up (and alert) eventually
    # TODO: time out a hung call, so it can't block the queue
    # TODO: a way to see what's stuck, and why
    while True:
        for event_id, user, video in conn.execute("SELECT id, user, video FROM like_events WHERE done = 0").fetchall():
            if not claim(conn, event_id, time.time()):
                continue  # another worker has it
            print(f"{event_id}", flush=True)
            try:
                process(conn, event_id, user, video)
            except Exception as error:  # noqa: BLE001 - left undone, tried again next pass
                print(f"  failed: {error!r}", flush=True)
                with conn:  # let it go, so the retry needn't wait out the timeout
                    conn.execute("UPDATE like_events SET claimed_at = NULL WHERE id = ?", (event_id,))
        time.sleep(0.5)


if __name__ == "__main__":
    print(f"worker starting. FAIL_RATE={chaos.FAIL_RATE}", flush=True)
    # Ctrl-C kills the worker outright, like a crash, instead of shutting down cleanly.
    signal.signal(signal.SIGINT, lambda *_: os._exit(130))
    run(connect())
