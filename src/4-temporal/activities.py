"""The steps that touch the outside world.

A worker can die after an activity's side effect lands but before Temporal hears
it finished. Temporal then runs the activity again, so each one has to be safe to run twice.
"""

import os

from temporalio import activity

import chaos
import db
from shared import LikeEvent


@activity.defn
def record_like(event: LikeEvent) -> None:
    # Safe to repeat: the same row either way.
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO reactions VALUES (?, ?, 'LIKE') "
            "ON CONFLICT (user, video) DO UPDATE SET reaction = 'LIKE'",
            (event.user, event.video),
        )
    activity.logger.info(f"{event.user} likes {event.video}")


@activity.defn
def update_like_count(video: str) -> int:
    with db.connect() as conn:
        if os.environ.get("COUNT_MODE") == "add":
            # Not safe to repeat: a retry after the crash below counts the like twice.
            conn.execute("UPDATE videos SET like_count = like_count + 1 WHERE id = ?", (video,))
        else:
            # Safe to repeat: SET the count from the reactions.
            conn.execute(
                "UPDATE videos SET like_count = "
                "(SELECT COUNT(*) FROM reactions WHERE video = ? AND reaction = 'LIKE') WHERE id = ?",
                (video, video),
            )
        count = db.like_count(conn, video)
    chaos.maybe_fail("after-count-commit")  # committed, but Temporal hasn't heard
    activity.logger.info(f"like count for {video}: {count}")
    return count


@activity.defn
def notify_creator(event: LikeEvent) -> bool:
    # The stable event ID lets the notification service drop a repeat.
    sent = db.send_notification(event.video, event.user, idempotency_key=event.event_id)
    chaos.maybe_fail("after-notify")  # sent, but Temporal hasn't heard
    activity.logger.info("creator notified" if sent else "repeat notification, ignored")
    return sent
