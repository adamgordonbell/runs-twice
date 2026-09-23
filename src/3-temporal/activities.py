"""Activities: the steps that touch the outside world.

Temporal records when an activity completes, but a worker can die after an
activity's side effect lands and before Temporal hears it finished. Temporal
then runs the activity again, so each one here must be safe to run twice.
"""

import os

from temporalio import activity

import chaos
import db
from shared import LikeEvent


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
    chaos.crash_point("after-count-commit")  # committed, but Temporal hasn't heard
    activity.logger.info(f"like count for {video}: {count}")
    return count


@activity.defn
def notify_creator(event: LikeEvent) -> bool:
    chaos.crash_point("before-notify")
    # The stable event ID lets the notification service drop a repeat.
    sent = db.send_notification(event.event_id, event.video, event.user)
    activity.logger.info("creator notified" if sent else "repeat notification, ignored")
    return sent
