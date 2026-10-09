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


def test_retry_after_a_failure_counts_twice_and_notifies_twice():
    chaos.fail_once("before-response")
    with pytest.raises(chaos.InjectedFailure):
        handle_like("alice", likes.VIDEO)
    handle_like("alice", likes.VIDEO)  # the client's retry
    with likes.connect() as conn:
        assert likes.count(conn) == 1206
        assert not likes.has_liked(conn, "alice")  # +1 never recorded who liked it
    assert len(notifications.sent(likes.VIDEO)) == 2
