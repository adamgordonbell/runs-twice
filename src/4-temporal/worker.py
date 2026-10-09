"""Stage 4 worker: runs the like workflow and its steps. Ctrl-C kills it like a crash."""

import asyncio
import logging
import os
import signal
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from temporalio.client import Client
from temporalio.worker import Worker

import chaos
from activities import notify_creator, record_like
from shared import TASK_QUEUE
from workflows import LikeWorkflow

MAX_ACTIVITIES = 4  # threads for activities, and the most the Worker will take on at once


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    print(f"worker starting. FAIL_RATE={chaos.FAIL_RATE} COUNT_MODE={os.environ.get('COUNT_MODE', 'set')!r}", flush=True)

    # Ctrl-C kills the worker outright, like a crash, instead of shutting down cleanly.
    signal.signal(signal.SIGINT, lambda *_: os._exit(130))

    client = await Client.connect("localhost:7233")
    with ThreadPoolExecutor(max_workers=MAX_ACTIVITIES) as executor:
        worker = Worker(
            client,
            task_queue=TASK_QUEUE,
            workflows=[LikeWorkflow],
            activities=[record_like, notify_creator],
            activity_executor=executor,
            max_concurrent_activities=MAX_ACTIVITIES,  # unset, it would take 100 on these 4 threads
            # A worker caches the workflows it ran and gets their next task first. If it
            # dies, the server waits this long before handing the task to another worker
            # (default 10s). Shortened so the demo recovers quickly.
            sticky_queue_schedule_to_start_timeout=timedelta(seconds=2),
        )
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
