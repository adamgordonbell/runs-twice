"""Stage 3: a like is saved as a note to finish the job. worker.py does the rest."""

import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

import chaos
import jobs
import likes
import notifications

app = FastAPI()


class Like(BaseModel):
    user: str
    video: str


def handle_like(user: str, video: str) -> str:
    event_id = f"like-{user}-{video}"
    with jobs.connect() as conn:
        jobs.add(conn, event_id, user, video)
    chaos.maybe_fail("after-commit")  # harmless here: the note is saved, and a retry finds it
    return event_id


@app.post("/like")
def like(like: Like) -> dict:
    return {"accepted": handle_like(like.user, like.video)}


@app.get("/videos/{video}")
def video_state(video: str, user: str = "alice") -> dict:
    with likes.connect() as conn:
        return {
            "likes": likes.count(conn, video),
            "liked": likes.has_liked(conn, user, video),
            "notifications": notifications.sent(video),
        }


@app.get("/")
def page() -> FileResponse:
    return FileResponse(Path(__file__).parents[2] / "client" / "like.html")


if __name__ == "__main__":
    if "--reset" in sys.argv or not likes.DB_PATH.exists():
        likes.reset()
        notifications.reset()
    uvicorn.run(app, port=8000, log_level="warning")
