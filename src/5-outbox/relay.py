"""The relay: hands each saved like to Temporal as a workflow, then checks it off. Safe to run twice: the workflow ID dedupes."""

import asyncio
import os
import signal
import sqlite3
import time

from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

import chaos
import outbox
from shared import TASK_QUEUE, LikeEvent
from workflows import NotifyWorkflow


async def hand_off(client: Client, conn: sqlite3.Connection, event_id: str, user: str, video: str) -> None:
    try:
        await client.start_workflow(
            NotifyWorkflow.run,
            LikeEvent(user, video),
            id=event_id,
            task_queue=TASK_QUEUE,
            id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )
    except WorkflowAlreadyStartedError:
        pass  # started on an earlier pass that died before checking it off
    chaos.maybe_fail("after-start")  # Temporal has it; the outbox doesn't know yet, so the next pass starts it again
    with conn:
        outbox.mark_sent(conn, event_id, time.time())


async def run(client: Client, conn: sqlite3.Connection) -> None:
    while True:
        for event_id, user, video in outbox.unsent(conn):
            try:
                await hand_off(client, conn, event_id, user, video)
            except Exception as error:  # noqa: BLE001 - left unsent, tried again next pass
                print(f"  {event_id} failed: {error!r}", flush=True)
        await asyncio.sleep(0.5)


async def main() -> None:
    print(f"relay starting. FAIL_RATE={chaos.FAIL_RATE}", flush=True)
    # Ctrl-C kills the relay outright, like a crash, instead of shutting down cleanly.
    signal.signal(signal.SIGINT, lambda *_: os._exit(130))
    client = await Client.connect("localhost:7233")
    await run(client, outbox.connect())


if __name__ == "__main__":
    asyncio.run(main())
