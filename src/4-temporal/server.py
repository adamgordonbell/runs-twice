"""Stage 4: a like starts a Temporal workflow, with an ID taken from the like."""

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
def video_state(video: str, user: str = "alice") -> dict:
    with db.connect() as conn:
        return {
            "likes": db.like_count(conn, video),
            "liked": db.has_liked(conn, user, video),
            "notifications": db.notifications(video),
        }


@app.get("/")
def page() -> FileResponse:
    return FileResponse(Path(__file__).parents[2] / "client" / "like.html")


if __name__ == "__main__":
    if "--reset" in sys.argv or not db.DB_PATH.exists():
        db.reset()
    uvicorn.run(app, port=8000, log_level="warning")
