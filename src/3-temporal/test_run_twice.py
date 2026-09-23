"""Temporal may run an activity twice, so each test runs one twice."""

import pytest
from temporalio.testing import ActivityEnvironment

import db
from activities import notify_creator, update_like_count
from shared import LikeEvent


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "likes.db")
    db.reset()


def test_update_like_count_twice():
    with db.connect() as conn:
        db.set_reaction(conn, "alice", db.VIDEO)
    env = ActivityEnvironment()
    assert env.run(update_like_count, db.VIDEO) == 1205
    assert env.run(update_like_count, db.VIDEO) == 1205


def test_notify_creator_twice():
    env = ActivityEnvironment()
    event = LikeEvent(user="alice", video=db.VIDEO)
    assert env.run(notify_creator, event) is True
    assert env.run(notify_creator, event) is False
    with db.connect() as conn:
        assert db.notification_count(conn) == 1
