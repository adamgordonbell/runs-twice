import pytest

import chaos
import db
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


def test_failure_after_commit_loses_the_notification():
    chaos.fail_once("after-commit")
    with pytest.raises(chaos.InjectedFailure):
        handle_like("alice", db.VIDEO)
    handle_like("alice", db.VIDEO)  # the client's retry
    with db.connect() as conn:
        assert db.like_count(conn) == 1205
    assert db.notifications() == []  # nobody told the creator
