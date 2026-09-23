from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from activities import notify_creator, update_like_count
    from shared import LikeEvent

# Short timeouts so a crashed worker is noticed in seconds during the demo.
ACTIVITY_OPTS = dict(
    start_to_close_timeout=timedelta(seconds=5),
    retry_policy=RetryPolicy(initial_interval=timedelta(seconds=1), maximum_interval=timedelta(seconds=5)),
)


@workflow.defn
class LikeWorkflow:
    """What a like causes. Temporal records each finished step, so a new worker resumes where the last one died."""

    @workflow.run
    async def run(self, event: LikeEvent) -> int:
        count = await workflow.execute_activity(update_like_count, event.video, **ACTIVITY_OPTS)
        await workflow.execute_activity(notify_creator, event, **ACTIVITY_OPTS)
        return count
