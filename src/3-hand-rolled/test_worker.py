import pytest

import chaos
import jobs
import likes
import notifications
import worker
from server import handle_like


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(likes, "DB_PATH", tmp_path / "likes.db")
    monkeypatch.setattr(notifications, "DB_PATH", tmp_path / "notifications.db")
    likes.reset()
    notifications.reset()


def test_retried_request_records_one_event():
    handle_like("alice", likes.VIDEO)
    handle_like("alice", likes.VIDEO)
    assert jobs.connect().execute("SELECT id FROM like_events").fetchall() == [("like-alice-video-123",)]


def test_failure_after_notify_then_rerun():
    event_id = handle_like("alice", likes.VIDEO)
    conn = jobs.connect()
    chaos.fail_once("after-notify")
    with pytest.raises(chaos.InjectedFailure):
        worker.process(conn, event_id, "alice", likes.VIDEO)
    worker.process(conn, event_id, "alice", likes.VIDEO)  # the next pass

    assert likes.count(conn) == 1205
    assert len(notifications.sent(likes.VIDEO)) == 1


def test_fresh_claim_keeps_other_workers_off():
    event_id = handle_like("alice", likes.VIDEO)
    conn = jobs.connect()
    assert jobs.claim(conn, event_id, now=1000)
    assert not jobs.claim(conn, event_id, now=1010)  # A is 10 s in: still A's


def test_slow_worker_and_takeover_both_run():
    event_id = handle_like("alice", likes.VIDEO)
    a, b = jobs.connect(), jobs.connect()
    assert jobs.claim(a, event_id, now=1000)
    chaos.fail_once("after-notify")  # A sends, then stalls before ticking it off
    with pytest.raises(chaos.InjectedFailure):
        worker.process(a, event_id, "alice", likes.VIDEO)

    assert jobs.claim(b, event_id, now=1031)  # 31 s of quiet: B takes over
    worker.process(b, event_id, "alice", likes.VIDEO)  # and sends again

    assert likes.count(a) == 1205
    assert len(notifications.sent(likes.VIDEO)) == 1
