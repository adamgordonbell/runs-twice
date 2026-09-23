"""The orchestrator's promises, each tested by running something twice or killing it halfway."""

import time

import pytest

import activities
import db
import orchestrator
from orchestrator import Orchestrator
from server import handle_like
from workflows import like_workflow


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "likes.db")
    monkeypatch.setattr(db, "NOTIFY_DB_PATH", tmp_path / "notifications.db")
    db.reset()


def jobs() -> list[tuple]:
    return orchestrator.connect().execute("SELECT id, status, attempts FROM jobs").fetchall()


def test_retried_request_queues_one_job():
    handle_like("alice", db.VIDEO)
    handle_like("alice", db.VIDEO)
    assert jobs() == [("like-alice-video-123", "pending", 0)]


def test_failed_step_is_retried_and_finished_steps_are_not(monkeypatch):
    calls = {"count": 0, "notify": 0}
    real_count, real_notify = activities.update_like_count, activities.notify_creator

    def count(video):
        calls["count"] += 1
        return real_count(video)

    def flaky_notify(event):
        calls["notify"] += 1
        if calls["notify"] == 1:
            raise ConnectionError("notification service down")
        return real_notify(event)

    monkeypatch.setattr("workflows.update_like_count", count)
    monkeypatch.setattr("workflows.notify_creator", flaky_notify)
    handle_like("alice", db.VIDEO)
    worker = Orchestrator({"like": like_workflow})

    worker.run_job(*worker.claim())  # count done, notify fails
    worker.conn.execute("UPDATE jobs SET next_run_at = 0")  # skip the backoff wait
    worker.conn.commit()
    worker.run_job(*worker.claim())  # count comes from history, notify succeeds

    assert calls == {"count": 1, "notify": 2}
    assert jobs() == [("like-alice-video-123", "done", 2)]
    assert len(db.notifications()) == 1


def test_expired_lease_moves_the_job_and_fences_the_old_worker():
    handle_like("alice", db.VIDEO)
    dead, alive = Orchestrator({"like": like_workflow}), Orchestrator({"like": like_workflow})
    dead.worker_id, alive.worker_id = "dead", "alive"

    assert dead.claim() is not None
    assert alive.claim() is None  # leased to the dead worker
    dead.conn.execute("UPDATE jobs SET lease_expires = ?", (time.time() - 1,))
    dead.conn.commit()

    job = alive.claim()
    assert job is not None and job[3] == 2  # second attempt
    ctx = orchestrator.Context(dead.conn, job[0], "dead")
    with pytest.raises(orchestrator.LeaseLost):
        ctx.step("update_like_count", activities.update_like_count, db.VIDEO)
