"""What happens if this runs twice? And what if it stops halfway?"""

import pytest

import db
import server
from server import handle_like


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "likes.db")
    monkeypatch.setattr(db, "NOTIFY_DB_PATH", tmp_path / "notifications.db")
    db.reset()


def test_retry_counts_once_and_notifies_once():
    handle_like("alice", db.VIDEO)
    handle_like("alice", db.VIDEO)
    with db.connect() as conn:
        assert db.like_count(conn) == 1205
    assert len(db.notifications()) == 1


def test_crash_after_commit_loses_the_notification(monkeypatch):
    crashes = ["after-commit"]  # crash the first request only, like CRASH_AT

    def crash_point(name):
        if name in crashes:
            crashes.remove(name)
            raise SystemExit(name)

    monkeypatch.setattr(server.chaos, "crash_point", crash_point)
    with pytest.raises(SystemExit):
        handle_like("alice", db.VIDEO)
    handle_like("alice", db.VIDEO)  # the client's retry
    with db.connect() as conn:
        assert db.like_count(conn) == 1205
    assert db.notifications() == []  # nobody told the creator
