"""Stage 4: the like's consequences run as a Temporal workflow.

The request stores the reaction, then starts a workflow whose ID comes from the
like. Both are safe to repeat, so the client can retry the whole request: the
reaction is the same row, and a second start finds the first workflow. A crash
between the two is covered too, because the retry starts the workflow anyway.

    temporal server start-dev --ui-port 8233                   # terminal 1, UI at http://localhost:8233
    uv run server.py --reset                                   # terminal 2
    uv run worker.py                                           # terminal 3
    uv run ../../client/client.py --lose-first-response --wait 2   # terminal 4
"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel
from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

import chaos
import db
from shared import TASK_QUEUE, LikeEvent
from workflows import LikeWorkflow

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.temporal = await Client.connect("localhost:7233")
    yield


app = FastAPI(lifespan=lifespan)


class Like(BaseModel):
    user: str
    video: str


async def handle_like(temporal: Client, user: str, video: str) -> str:
    event = LikeEvent(user, video)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO reactions VALUES (?, ?, 'LIKE') "
            "ON CONFLICT (user, video) DO UPDATE SET reaction = 'LIKE'",
            (user, video),
        )
    chaos.crash_point("after-commit")  # the like is saved, no workflow yet; the client's retry starts it
    try:
        await temporal.start_workflow(
            LikeWorkflow.run,
            event,
            id=event.event_id,
            task_queue=TASK_QUEUE,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )
    except WorkflowAlreadyStartedError:
        pass  # a retried request: the workflow for this like already exists
    return event.event_id


@app.post("/like")
async def like(like: Like) -> dict:
    return {"accepted": await handle_like(app.state.temporal, like.user, like.video)}


@app.get("/videos/{video}")
def video_state(video: str) -> dict:
    with db.connect() as conn:
        return {"likes": db.like_count(conn, video), "notifications": db.notifications(video)}


@app.get("/")
def page() -> FileResponse:
    return FileResponse(Path(__file__).parents[2] / "client" / "like.html")


if __name__ == "__main__":
    if "--reset" in sys.argv or not db.DB_PATH.exists():
        db.reset()
    uvicorn.run(app, port=8000, log_level="warning")
