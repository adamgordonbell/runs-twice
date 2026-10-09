"""Temporal may run an activity twice, so each test runs one twice."""

import pytest
from temporalio.testing import ActivityEnvironment

import chaos
import likes
import notifications
from activities import notify_creator, record_like
from shared import LikeEvent


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(likes, "DB_PATH", tmp_path / "likes.db")
    monkeypatch.setattr(notifications, "DB_PATH", tmp_path / "notifications.db")
    likes.reset()
    notifications.reset()


def test_record_like_twice():
    env = ActivityEnvironment()
    event = LikeEvent(user="alice", video=likes.VIDEO)
    assert env.run(record_like, event) == 1205
    assert env.run(record_like, event) == 1205
    with likes.connect() as conn:
        assert likes.has_liked(conn, "alice")
        assert conn.execute("SELECT COUNT(*) FROM reactions WHERE user = 'alice'").fetchone()[0] == 1


def test_notify_creator_twice():
    env = ActivityEnvironment()
    event = LikeEvent(user="alice", video=likes.VIDEO)
    assert env.run(notify_creator, event) is True
    assert env.run(notify_creator, event) is False
    assert len(notifications.sent(likes.VIDEO)) == 1


def test_add_counts_twice_when_the_activity_fails_after_commit(monkeypatch):
    monkeypatch.setenv("COUNT_MODE", "add")
    env = ActivityEnvironment()
    event = LikeEvent(user="alice", video=likes.VIDEO)
    chaos.fail_once("after-commit")
    with pytest.raises(chaos.InjectedFailure):
        env.run(record_like, event)
    env.run(record_like, event)  # Temporal's retry
    with likes.connect() as conn:
        assert likes.count(conn) == 1206
