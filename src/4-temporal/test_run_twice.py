"""Temporal may run an activity twice, so each test runs one twice."""

import pytest
from temporalio.testing import ActivityEnvironment

import chaos
import db
from activities import notify_creator, record_like, update_like_count
from shared import LikeEvent


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "likes.db")
    monkeypatch.setattr(db, "NOTIFY_DB_PATH", tmp_path / "notifications.db")
    db.reset()


def test_record_like_twice():
    env = ActivityEnvironment()
    event = LikeEvent(user="alice", video=db.VIDEO)
    env.run(record_like, event)
    env.run(record_like, event)
    with db.connect() as conn:
        assert db.has_liked(conn, "alice")
        assert conn.execute("SELECT COUNT(*) FROM reactions WHERE user = 'alice'").fetchone()[0] == 1


def test_update_like_count_twice():
    ActivityEnvironment().run(record_like, LikeEvent(user="alice", video=db.VIDEO))
    env = ActivityEnvironment()
    assert env.run(update_like_count, db.VIDEO) == 1205
    assert env.run(update_like_count, db.VIDEO) == 1205


def test_notify_creator_twice():
    env = ActivityEnvironment()
    event = LikeEvent(user="alice", video=db.VIDEO)
    assert env.run(notify_creator, event) is True
    assert env.run(notify_creator, event) is False
    assert len(db.notifications()) == 1


def test_add_counts_twice_when_the_activity_fails_after_commit(monkeypatch):
    monkeypatch.setenv("COUNT_MODE", "add")
    env = ActivityEnvironment()
    chaos.fail_once("after-count-commit")
    with pytest.raises(chaos.InjectedFailure):
        env.run(update_like_count, db.VIDEO)
    env.run(update_like_count, db.VIDEO)  # Temporal's retry
    with db.connect() as conn:
        assert db.like_count(conn) == 1206
