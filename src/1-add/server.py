"""Stage 1: a like is +1. What happens if this runs twice?

    uv run server.py --reset                                   # terminal 1
    uv run ../../client/client.py --lose-first-response        # terminal 2, or open http://localhost:8000
    FAIL_RATE=0.5 uv run server.py --reset                     # or: the server fails after doing the work
"""

import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

import chaos
import db

app = FastAPI()


class Like(BaseModel):
    user: str
    video: str


def handle_like(user: str, video: str) -> int:
    with db.connect() as conn:
        conn.execute("UPDATE videos SET like_count = like_count + 1 WHERE id = ?", (video,))
        count = db.like_count(conn, video)
    db.send_notification(video, user)
    chaos.maybe_fail("before-response")  # the work is done; the client gets an error and retries
    return count


@app.post("/like")
def like(like: Like) -> dict:
    return {"likes": handle_like(like.user, like.video)}


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
