"""What happens if this runs twice? And what if it stops halfway?"""

import pytest

import chaos
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


def test_failure_after_notify_then_rerun():
    event_id = handle_like("alice", db.VIDEO)
    conn = connect()
    chaos.fail_once("after-notify")
    with pytest.raises(chaos.InjectedFailure):
        worker.process(conn, event_id, "alice", db.VIDEO)
    worker.process(conn, event_id, "alice", db.VIDEO)  # the next pass

    assert db.like_count(conn) == 1205
    assert len(db.notifications()) == 1
