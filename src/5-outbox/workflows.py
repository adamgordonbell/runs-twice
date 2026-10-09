"""The notify workflow: one step. Temporal retries it until it finishes."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from activities import notify_creator
    from shared import LikeEvent

# Short timeouts so a crashed worker is noticed in seconds during the demo.
ACTIVITY_OPTS = dict(
    start_to_close_timeout=timedelta(seconds=5),
    retry_policy=RetryPolicy(initial_interval=timedelta(seconds=1), maximum_interval=timedelta(seconds=5)),
)


@workflow.defn
class NotifyWorkflow:
    @workflow.run
    async def run(self, event: LikeEvent) -> bool:
        return await workflow.execute_activity(notify_creator, event, **ACTIVITY_OPTS)
