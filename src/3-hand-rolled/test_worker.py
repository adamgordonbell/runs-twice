"""What happens if this runs twice? And what if it stops halfway?"""

import pytest

import db
import worker
from server import connect, handle_like


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "likes.db")
    monkeypatch.setattr(db, "NOTIFY_DB_PATH", tmp_path / "notifications.db")
    db.reset()


def test_retried_request_records_one_event():
    handle_like("alice", db.VIDEO)
    handle_like("alice", db.VIDEO)
    assert connect().execute("SELECT id FROM like_events").fetchall() == [("like-alice-video-123",)]


def test_crash_after_notify_then_rerun(monkeypatch):
    crashes = ["after-notify"]  # crash the first run only, like CRASH_AT

    def crash_point(name):
        if name in crashes:
            crashes.remove(name)
            raise SystemExit(name)

    monkeypatch.setattr(worker.chaos, "crash_point", crash_point)
    event_id = handle_like("alice", db.VIDEO)
    conn = connect()
    with pytest.raises(SystemExit):
        worker.process(conn, event_id, "alice", db.VIDEO)
    worker.process(connect(), event_id, "alice", db.VIDEO)  # a fresh worker picks it up

    assert db.like_count(conn) == 1205
    assert len(db.notifications()) == 1
