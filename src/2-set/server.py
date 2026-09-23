"""Stage 2: a like is state. Running it twice is safe, but a crash can lose the notification.

The like is stored as (user, video) = LIKE and the count is SET from the
reactions, so a retry changes nothing. The creator is notified only when the
reaction actually changed, so a retry sends nothing new either.

    uv run server.py --reset                                   # terminal 1
    uv run ../../client/client.py --lose-first-response        # terminal 2: 1205 likes, 1 notification

The gap: the database commit and the notification are two systems. Crash between them:

    CRASH_AT=after-commit uv run server.py --reset             # terminal 1
    uv run ../../client/client.py                              # terminal 2: the server dies mid-request
    uv run server.py                                           # terminal 1 again, while the client retries
    # -> 1205 likes, 0 notifications. The retry saw nothing to change, so nobody told the creator.
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
    chaos.crash_point("after-commit")  # the like is saved; the notification isn't sent yet
    if changed:
        db.send_notification(video, user)
    return count


@app.post("/like")
def like(like: Like) -> dict:
    return {"likes": handle_like(like.user, like.video)}


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
