"""Stage 5: a like is saved with its count and a note for the relay, all in one transaction. No Temporal here."""

import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

import chaos
import likes
import notifications
import outbox
from shared import LikeEvent

app = FastAPI()


class Like(BaseModel):
    user: str
    video: str


def handle_like(user: str, video: str) -> int:
    event = LikeEvent(user, video)
    with outbox.connect() as conn:  # the like, its count and the note commit together, or not at all
        likes.add_reaction(conn, user, video)
        likes.recount(conn, video)
        outbox.add(conn, event.event_id, user, video)
        count = likes.count(conn, video)
    chaos.maybe_fail("after-commit")  # harmless here: the note is saved, so the relay will still tell Temporal
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
