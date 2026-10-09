"""Stage 2: a like is a fact. The notification is a second system."""

import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

import chaos
import likes
import notifications

app = FastAPI()


class Like(BaseModel):
    user: str
    video: str


def handle_like(user: str, video: str) -> int:
    with likes.connect() as conn:
        changed = likes.add_reaction(conn, user, video)
        likes.recount(conn, video)
        count = likes.count(conn, video)
    chaos.maybe_fail("after-commit")  # the like is saved; the notification isn't sent yet
    if changed:
        notifications.send(video, user)
    return count


@app.post("/like")
def like(like: Like) -> dict:
    return {"likes": handle_like(like.user, like.video)}


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
