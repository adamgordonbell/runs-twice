"""The Like request handler, with Temporal.

It stores the reaction, then starts a workflow for the downstream work. Both
steps are safe to repeat, so the client can retry the whole request:
set_reaction leaves the same row, and the workflow ID comes from the like, so a
second start finds the first workflow instead of creating another.

    uv run starter.py            # Alice likes the video
    uv run starter.py --retry    # the response is lost and the client sends it again
"""

import argparse
import asyncio

from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

import db
from shared import TASK_QUEUE, LikeEvent
from workflows import LikeWorkflow


async def handle_like(client: Client, event: LikeEvent) -> None:
    with db.connect() as conn:
        db.set_reaction(conn, event.user, event.video)
    try:
        await client.start_workflow(
            LikeWorkflow.run,
            event,
            id=event.event_id,
            task_queue=TASK_QUEUE,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )
        print(f"started workflow {event.event_id}")
    except WorkflowAlreadyStartedError:
        print(f"workflow {event.event_id} already exists, nothing to do")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default="alice")
    parser.add_argument("--retry", action="store_true", help="send the same request twice")
    args = parser.parse_args()

    client = await Client.connect("localhost:7233")
    event = LikeEvent(user=args.user, video=db.VIDEO)
    with db.connect() as conn:
        print(f"{db.like_count(conn)} likes, {event.user} clicks once")

    await handle_like(client, event)
    if args.retry:
        print("response lost, client retries")
        await handle_like(client, event)

    count = await client.get_workflow_handle(event.event_id).result()
    with db.connect() as conn:
        print(f"-> {count} likes, {db.notification_count(conn)} notification(s)")


if __name__ == "__main__":
    asyncio.run(main())
