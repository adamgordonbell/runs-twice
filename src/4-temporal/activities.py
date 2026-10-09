"""The workflow's steps. Temporal may run any of them twice."""

import os

from temporalio import activity

import chaos
import likes
import notifications
from shared import LikeEvent


@activity.defn
def record_like(event: LikeEvent) -> int:
    # The like and its count commit together, so they can't disagree.
    with likes.connect() as conn:
        likes.add_reaction(conn, event.user, event.video)
        if os.environ.get("COUNT_MODE") == "add":
            # Not safe to repeat: a retry after the crash below counts the like twice.
            likes.increment(conn, event.video)
        else:
            # Safe to repeat: SET the count from the reactions.
            likes.recount(conn, event.video)
        count = likes.count(conn, event.video)
    chaos.maybe_fail("after-commit")  # committed, but Temporal hasn't heard
    activity.logger.info(f"{event.user} likes {event.video}: count {count}")
    return count


@activity.defn
def notify_creator(event: LikeEvent) -> bool:
    # The stable event ID lets the notification service drop a repeat.
    sent = notifications.send(event.video, event.user, idempotency_key=event.event_id)
    chaos.maybe_fail("after-notify")  # sent, but Temporal hasn't heard
    activity.logger.info("creator notified" if sent else "repeat notification, ignored")
    return sent
