import pytest

import chaos
import likes
import notifications
from server import handle_like


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(likes, "DB_PATH", tmp_path / "likes.db")
    monkeypatch.setattr(notifications, "DB_PATH", tmp_path / "notifications.db")
    likes.reset()
    notifications.reset()


def test_retry_counts_once_and_notifies_once():
    handle_like("alice", likes.VIDEO)
    handle_like("alice", likes.VIDEO)
    with likes.connect() as conn:
        assert likes.count(conn) == 1205
    assert len(notifications.sent(likes.VIDEO)) == 1


def test_failure_after_commit_loses_the_notification():
    chaos.fail_once("after-commit")
    with pytest.raises(chaos.InjectedFailure):
        handle_like("alice", likes.VIDEO)
    handle_like("alice", likes.VIDEO)  # the client's retry
    with likes.connect() as conn:
        assert likes.count(conn) == 1205
    assert notifications.sent(likes.VIDEO) == []  # nobody told the creator
