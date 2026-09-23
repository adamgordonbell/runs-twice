"""What happens if this runs twice?"""

import pytest

import db
from server import handle_like


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "likes.db")
    monkeypatch.setattr(db, "NOTIFY_DB_PATH", tmp_path / "notifications.db")
    db.reset()


def test_retry_counts_twice_and_notifies_twice():
    handle_like("alice", db.VIDEO)
    handle_like("alice", db.VIDEO)
    with db.connect() as conn:
        assert db.like_count(conn) == 1206
    assert len(db.notifications()) == 2
