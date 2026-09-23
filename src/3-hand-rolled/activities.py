"""The steps that touch the outside world.

The orchestrator records when a step completes, but a worker can die after a
step's side effect lands and before the orchestrator records it. The next worker
then runs the step again, so each one here must be safe to run twice.
"""

import os

import chaos
import db
from shared import LikeEvent


def update_like_count(video: str) -> int:
    with db.connect() as conn:
        if os.environ.get("COUNT_MODE") == "add":
            # Not safe to repeat: a rerun after the crash below counts the like twice.
            conn.execute("UPDATE videos SET like_count = like_count + 1 WHERE id = ?", (video,))
        else:
            # Safe to repeat: SET the count from the reactions.
            conn.execute(
                "UPDATE videos SET like_count = "
                "(SELECT COUNT(*) FROM reactions WHERE video = ? AND reaction = 'LIKE') WHERE id = ?",
                (video, video),
            )
        count = db.like_count(conn, video)
    chaos.crash_point("after-count-commit")  # committed, but the orchestrator hasn't recorded it
    print(f"  like count for {video}: {count}", flush=True)
    return count


def notify_creator(event: LikeEvent) -> bool:
    chaos.crash_point("before-notify")
    # The stable event ID lets the notification service drop a repeat.
    sent = db.send_notification(event.video, event.user, idempotency_key=event.event_id)
    print("  creator notified" if sent else "  repeat notification, ignored", flush=True)
    return sent
