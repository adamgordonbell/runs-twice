import asyncio
import logging
import os
import signal
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from temporalio.client import Client
from temporalio.worker import Worker

import chaos
from activities import notify_creator, record_like, update_like_count
from shared import TASK_QUEUE
from workflows import LikeWorkflow


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    print(f"worker starting. FAIL_RATE={chaos.FAIL_RATE} COUNT_MODE={os.environ.get('COUNT_MODE', 'set')!r}", flush=True)

    # Ctrl-C kills the worker outright, like a crash, instead of shutting down cleanly.
    signal.signal(signal.SIGINT, lambda *_: os._exit(130))

    client = await Client.connect("localhost:7233")
    with ThreadPoolExecutor(max_workers=4) as executor:
        worker = Worker(
            client,
            task_queue=TASK_QUEUE,
            workflows=[LikeWorkflow],
            activities=[record_like, update_like_count, notify_creator],
            activity_executor=executor,
            # A worker caches the workflows it ran and gets their next task first. If it
            # dies, the server waits this long before handing the task to another worker
            # (default 10s). Shortened so the demo recovers quickly.
            sticky_queue_schedule_to_start_timeout=timedelta(seconds=2),
        )
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
