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


def test_fresh_claim_keeps_other_workers_off():
    event_id = handle_like("alice", db.VIDEO)
    conn = connect()
    assert worker.claim(conn, event_id, now=1000)
    assert not worker.claim(conn, event_id, now=1010)  # A is 10 s in: still A's


def test_slow_worker_and_takeover_both_run():
    event_id = handle_like("alice", db.VIDEO)
    a, b = connect(), connect()
    assert worker.claim(a, event_id, now=1000)
    chaos.fail_once("after-notify")  # A sends, then stalls before ticking it off
    with pytest.raises(chaos.InjectedFailure):
        worker.process(a, event_id, "alice", db.VIDEO)

    assert worker.claim(b, event_id, now=1031)  # 31 s of quiet: B takes over
    worker.process(b, event_id, "alice", db.VIDEO)  # and sends again

    assert db.like_count(a) == 1205
    assert len(db.notifications()) == 1
