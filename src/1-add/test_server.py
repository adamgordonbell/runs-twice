import pytest

import chaos
import db
from server import handle_like


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "likes.db")
    monkeypatch.setattr(db, "NOTIFY_DB_PATH", tmp_path / "notifications.db")
    db.reset()


def test_retry_after_a_failure_counts_twice_and_notifies_twice():
    chaos.fail_once("before-response")
    with pytest.raises(chaos.InjectedFailure):
        handle_like("alice", db.VIDEO)
    handle_like("alice", db.VIDEO)  # the client's retry
    with db.connect() as conn:
        assert db.like_count(conn) == 1206
        assert not db.has_liked(conn, "alice")  # +1 never recorded who liked it
    assert len(db.notifications()) == 2
