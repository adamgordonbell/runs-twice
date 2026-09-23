"""A small durable workflow engine: the layer Temporal factors out.

It knows nothing about likes. Given a workflow (a function that runs steps), it
gives you:

- A queue.         enqueue() adds a job inside the caller's transaction, so the job
                   exists if and only if the caller's change committed.
- One job ID.      enqueue() ignores a job ID it already has, so a retried request
                   doesn't queue the work twice.
- Leases.          A worker claims a job for LEASE_SECONDS. If it dies, the lease
                   runs out and another worker takes the job over.
- Step history.    ctx.step() records each finished step. When a job runs again,
                   finished steps return their recorded result instead of rerunning.
- Retries.         A failing job is retried with backoff, up to MAX_ATTEMPTS.
- Fencing.         A worker that lost its lease can't record results.
- Visibility.      `uv run orchestrator.py` lists the jobs.

What it still doesn't have, and Temporal does: timers and sleeps that survive a
restart, signals and queries, cancellation, versioning for workflows already in
flight, a UI, and anything past one SQLite file and one machine's clock.

Leases have one hole no engine can close: a worker can finish a step's side effect
and die before recording it. The next worker runs that step again. So steps must
be safe to run twice.
"""

import json
import os
import socket
import sqlite3
import time
from collections.abc import Callable
from typing import Any

import db

LEASE_SECONDS = 5
MAX_ATTEMPTS = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    workflow      TEXT NOT NULL,
    input         TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending | running | done | failed
    attempts      INTEGER NOT NULL DEFAULT 0,
    next_run_at   REAL NOT NULL DEFAULT 0,
    lease_owner   TEXT,
    lease_expires REAL,
    error         TEXT
);
CREATE TABLE IF NOT EXISTS step_history (
    job_id TEXT NOT NULL,
    step   TEXT NOT NULL,
    result TEXT NOT NULL,
    PRIMARY KEY (job_id, step)
);
"""


def connect() -> sqlite3.Connection:
    conn = db.connect()
    conn.executescript(SCHEMA)
    return conn


def enqueue(conn: sqlite3.Connection, job_id: str, workflow: str, input: dict) -> None:
    """Add a job. Call inside the caller's transaction; a job ID already queued is ignored.

    The caller's connection must come from connect(), which creates the tables.
    """
    conn.execute(
        "INSERT INTO jobs (id, workflow, input) VALUES (?, ?, ?) ON CONFLICT (id) DO NOTHING",
        (job_id, workflow, json.dumps(input)),
    )


class LeaseLost(Exception):
    """Another worker took the job over; this one must stop."""


class Context:
    """Handed to a workflow. ctx.step() is the only way a workflow does work."""

    def __init__(self, conn: sqlite3.Connection, job_id: str, worker_id: str):
        self.conn, self.job_id, self.worker_id = conn, job_id, worker_id

    def step(self, name: str, fn: Callable[..., Any], *args: Any) -> Any:
        row = self.conn.execute(
            "SELECT result FROM step_history WHERE job_id = ? AND step = ?", (self.job_id, name)
        ).fetchone()
        if row:
            print(f"  {name}: already done, using the recorded result", flush=True)
            return json.loads(row[0])

        with self.conn:
            self._renew_lease()
        result = fn(*args)
        with self.conn:  # fencing: the lease check and the record commit together
            self._renew_lease()
            self.conn.execute(
                "INSERT INTO step_history VALUES (?, ?, ?)", (self.job_id, name, json.dumps(result))
            )
        print(f"  {name}: done", flush=True)
        return result

    def _renew_lease(self) -> None:
        cur = self.conn.execute(
            "UPDATE jobs SET lease_expires = ? WHERE id = ? AND lease_owner = ? AND status = 'running'",
            (time.time() + LEASE_SECONDS, self.job_id, self.worker_id),
        )
        if cur.rowcount == 0:
            raise LeaseLost(self.job_id)


class Orchestrator:
    def __init__(self, workflows: dict[str, Callable[..., Any]]):
        self.workflows = workflows
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}"
        self.conn = connect()

    def claim(self) -> tuple[str, str, str, int] | None:
        """Take the next job that is due, or one whose worker's lease ran out. One statement, so atomic."""
        now = time.time()
        with self.conn:
            return self.conn.execute(
                """
                UPDATE jobs SET status = 'running', lease_owner = ?, lease_expires = ?, attempts = attempts + 1
                WHERE id = (
                    SELECT id FROM jobs
                    WHERE (status = 'pending' AND next_run_at <= ?)
                       OR (status = 'running' AND lease_expires < ?)
                    ORDER BY next_run_at LIMIT 1
                )
                RETURNING id, workflow, input, attempts
                """,
                (self.worker_id, now + LEASE_SECONDS, now, now),
            ).fetchone()

    def run_job(self, job_id: str, workflow: str, input: str, attempts: int) -> None:
        print(f"{job_id}: attempt {attempts}", flush=True)
        try:
            self.workflows[workflow](Context(self.conn, job_id, self.worker_id), json.loads(input))
        except LeaseLost:
            print(f"{job_id}: lease lost to another worker, stopping", flush=True)
            return
        except Exception as error:  # noqa: BLE001 - any failure is retried
            self.conn.rollback()
            done = attempts >= MAX_ATTEMPTS
            delay = min(2**attempts, 30)
            with self.conn:
                self.conn.execute(
                    "UPDATE jobs SET status = ?, next_run_at = ?, lease_owner = NULL, error = ? "
                    "WHERE id = ? AND lease_owner = ?",
                    ("failed" if done else "pending", time.time() + delay, repr(error), job_id, self.worker_id),
                )
            print(f"{job_id}: {error!r}, " + ("giving up" if done else f"retrying in {delay}s"), flush=True)
            return
        with self.conn:
            self.conn.execute(
                "UPDATE jobs SET status = 'done', lease_owner = NULL WHERE id = ? AND lease_owner = ?",
                (job_id, self.worker_id),
            )
        print(f"{job_id}: done", flush=True)

    def run_forever(self, poll_seconds: float = 0.5) -> None:
        print(f"worker {self.worker_id} polling for jobs", flush=True)
        while True:
            job = self.claim()
            if job:
                self.run_job(*job)
            else:
                time.sleep(poll_seconds)


if __name__ == "__main__":
    for row in connect().execute("SELECT id, status, attempts, lease_owner, error FROM jobs ORDER BY rowid"):
        print(" | ".join(str(v) for v in row))
