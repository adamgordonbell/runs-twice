"""Stage 3: the like's consequences run as a workflow, on an orchestrator we wrote.

The request stores the reaction and queues a job in one transaction, so the job
exists if and only if the like does. A worker runs the job: update the count,
then notify the creator. See orchestrator.py for what that takes.

    uv run server.py --reset                                   # terminal 1
    uv run worker.py                                           # terminal 2 (run two, if you like)
    uv run ../../client/client.py --lose-first-response --wait 2   # terminal 3
"""

import sys
from dataclasses import asdict
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

import chaos
import db
import orchestrator
from shared import LikeEvent

app = FastAPI()


class Like(BaseModel):
    user: str
    video: str


def handle_like(user: str, video: str) -> str:
    event = LikeEvent(user, video)
    with orchestrator.connect() as conn:
        conn.execute(
            "INSERT INTO reactions VALUES (?, ?, 'LIKE') "
            "ON CONFLICT (user, video) DO UPDATE SET reaction = 'LIKE'",
            (user, video),
        )
        orchestrator.enqueue(conn, event.event_id, "like", asdict(event))
    chaos.crash_point("after-commit")  # harmless here: the like and its job committed together
    return event.event_id


@app.post("/like")
def like(like: Like) -> dict:
    return {"accepted": handle_like(like.user, like.video)}


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
