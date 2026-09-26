"""Stage 3: the like and a note to finish the job commit together. worker.py does the rest."""

import sqlite3
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

import chaos
import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS like_events (
    id    TEXT PRIMARY KEY,
    user  TEXT NOT NULL,
    video TEXT NOT NULL,
    done  INTEGER NOT NULL DEFAULT 0,
    claimed_at REAL  -- when a worker took it; NULL = nobody has
);
CREATE TABLE IF NOT EXISTS steps_done (
    event_id TEXT NOT NULL,
    step     TEXT NOT NULL,
    PRIMARY KEY (event_id, step)
);
"""


def connect() -> sqlite3.Connection:
    conn = db.connect()
    conn.executescript(SCHEMA)
    return conn


app = FastAPI()


class Like(BaseModel):
    user: str
    video: str


def handle_like(user: str, video: str) -> str:
    event_id = f"like-{user}-{video}"
    with connect() as conn:
        conn.execute(
            "INSERT INTO reactions VALUES (?, ?, 'LIKE') "
            "ON CONFLICT (user, video) DO UPDATE SET reaction = 'LIKE'",
            (user, video),
        )
        conn.execute(
            "INSERT INTO like_events (id, user, video) VALUES (?, ?, ?) ON CONFLICT (id) DO NOTHING",
            (event_id, user, video),
        )
    chaos.maybe_fail("after-commit")  # harmless here: the like and its event committed together
    return event_id


@app.post("/like")
def like(like: Like) -> dict:
    return {"accepted": handle_like(like.user, like.video)}


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
