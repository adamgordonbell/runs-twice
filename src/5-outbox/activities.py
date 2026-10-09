"""The workflow's one step. Temporal may run it twice."""

from temporalio import activity

import chaos
import notifications
from shared import LikeEvent


@activity.defn
def notify_creator(event: LikeEvent) -> bool:
    # The like is already saved: the relay only starts this after the transaction that wrote it committed.
    # The stable event ID lets the notification service drop a repeat.
    sent = notifications.send(event.video, event.user, idempotency_key=event.event_id)
    chaos.maybe_fail("after-notify")  # sent, but Temporal hasn't heard
    activity.logger.info("creator notified" if sent else "repeat notification, ignored")
    return sent
