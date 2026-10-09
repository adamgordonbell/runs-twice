"""Stage 3 worker: finishes each noted like, one checked-off step at a time."""

import os
import signal
import sqlite3
import time

import chaos
import jobs
import likes
import notifications


def process(conn: sqlite3.Connection, event_id: str, user: str, video: str) -> None:
    if not jobs.step_done(conn, event_id, "record"):
        with conn:  # the like, the count and their checkmark commit together, so they can't disagree
            likes.add_reaction(conn, user, video)
            likes.recount(conn, video)
            jobs.mark_done(conn, event_id, "record")
        print(f"  like recorded, count: {likes.count(conn, video)}", flush=True)

    if not jobs.step_done(conn, event_id, "notify"):
        chaos.maybe_fail("before-notify")
        # Another system, so it can't share our transaction. A crash between sending and
        # the checkmark sends again on the rerun; safe only because the service drops a repeated key.
        sent = notifications.send(video, user, idempotency_key=event_id)
        chaos.maybe_fail("after-notify")
        with conn:
            jobs.mark_done(conn, event_id, "notify")
        print("  creator notified" if sent else "  repeat notification, ignored", flush=True)

    with conn:
        jobs.finish(conn, event_id)


def run(conn: sqlite3.Connection) -> None:
    # TODO: retry with backoff, and give up (and alert) eventually
    # TODO: time out a hung call, so it can't block the queue
    # TODO: a way to see what's stuck, and why
    while True:
        for event_id, user, video in jobs.pending(conn):
            if not jobs.claim(conn, event_id, time.time()):
                continue  # another worker has it
            print(f"{event_id}", flush=True)
            try:
                process(conn, event_id, user, video)
            except Exception as error:  # noqa: BLE001 - left undone, tried again next pass
                print(f"  failed: {error!r}", flush=True)
                with conn:  # let it go, so the retry needn't wait out the timeout
                    jobs.release(conn, event_id)
        time.sleep(0.5)


if __name__ == "__main__":
    print(f"worker starting. FAIL_RATE={chaos.FAIL_RATE}", flush=True)
    # Ctrl-C kills the worker outright, like a crash, instead of shutting down cleanly.
    signal.signal(signal.SIGINT, lambda *_: os._exit(130))
    run(jobs.connect())
