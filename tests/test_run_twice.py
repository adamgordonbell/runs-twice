"""Each test asks the video's question: what happens if this runs twice?"""

from temporalio.testing import ActivityEnvironment

import db
import naive
from activities import notify_creator, update_like_count
from shared import LikeEvent


def test_add_twice_counts_twice():
    with db.connect() as conn:
        naive.click_like(naive.like_add, conn)
        assert db.like_count(conn) == 1206


def test_set_twice_counts_once():
    with db.connect() as conn:
        naive.click_like(naive.like_set, conn)
        assert db.like_count(conn) == 1205


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
