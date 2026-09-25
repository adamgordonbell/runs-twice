"""Stage 2: a like is state, so running it twice is safe. But the commit and the
notification are two systems; crash between them and the retry can't tell.

    uv run server.py --reset                                   # terminal 1
    uv run ../../client/client.py --lose-first-response        # terminal 2: 1205 likes, 1 notification
    FAIL_RATE=1 uv run server.py --reset                       # every request fails after the commit: 1205, 0 notifications
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
        changed = conn.execute(
            "INSERT INTO reactions VALUES (?, ?, 'LIKE') "
            "ON CONFLICT (user, video) DO UPDATE SET reaction = 'LIKE' WHERE reaction <> 'LIKE'",
            (user, video),
        ).rowcount == 1
        conn.execute(
            "UPDATE videos SET like_count = "
            "(SELECT COUNT(*) FROM reactions WHERE video = ? AND reaction = 'LIKE') WHERE id = ?",
            (video, video),
        )
        count = db.like_count(conn, video)
    chaos.maybe_fail("after-commit")  # the like is saved; the notification isn't sent yet
    if changed:
        db.send_notification(video, user)
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
