"""The like is saved with a note for the relay. The relay may run twice; so may the step it starts."""

import asyncio

import pytest
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.testing import ActivityEnvironment

import chaos
import likes
import notifications
import outbox
import relay
from activities import notify_creator
from server import handle_like
from shared import LikeEvent


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(likes, "DB_PATH", tmp_path / "likes.db")
    monkeypatch.setattr(notifications, "DB_PATH", tmp_path / "notifications.db")
    likes.reset()
    notifications.reset()


class FakeTemporal:
    """Starts a workflow once per ID, like Temporal does, and remembers each start."""

    def __init__(self):
        self.started: list[str] = []

    async def start_workflow(self, run, event, *, id, **_):
        if id in self.started:
            raise WorkflowAlreadyStartedError(id, "NotifyWorkflow")
        self.started.append(id)


def test_retried_request_saves_one_note_and_counts_once():
    handle_like("alice", likes.VIDEO)
    handle_like("alice", likes.VIDEO)
    conn = outbox.connect()
    assert conn.execute("SELECT id FROM outbox").fetchall() == [("like-alice-video-123",)]
    assert likes.count(conn) == 1205


def test_failure_after_commit_still_leaves_a_note_for_the_relay():
    chaos.fail_once("after-commit")
    with pytest.raises(chaos.InjectedFailure):
        handle_like("alice", likes.VIDEO)
    conn = outbox.connect()
    assert likes.count(conn) == 1205
    assert [row[0] for row in outbox.unsent(conn)] == ["like-alice-video-123"]  # stage 2 lost this for good


def test_relay_hands_off_and_checks_off():
    handle_like("alice", likes.VIDEO)
    conn, temporal = outbox.connect(), FakeTemporal()
    for event_id, user, video in outbox.unsent(conn):
        asyncio.run(relay.hand_off(temporal, conn, event_id, user, video))
    assert temporal.started == ["like-alice-video-123"]
    assert outbox.unsent(conn) == []


def test_relay_dies_after_starting_then_runs_again():
    handle_like("alice", likes.VIDEO)
    conn, temporal = outbox.connect(), FakeTemporal()
    (event_id, user, video), = outbox.unsent(conn)
    chaos.fail_once("after-start")
    with pytest.raises(chaos.InjectedFailure):
        asyncio.run(relay.hand_off(temporal, conn, event_id, user, video))
    assert outbox.unsent(conn) != []  # started, but not checked off
    asyncio.run(relay.hand_off(temporal, conn, event_id, user, video))  # the next pass starts it again
    assert temporal.started == ["like-alice-video-123"]  # Temporal refused the second start
    assert outbox.unsent(conn) == []


def test_notify_creator_twice():
    env = ActivityEnvironment()
    event = LikeEvent(user="alice", video=likes.VIDEO)
    assert env.run(notify_creator, event) is True
    assert env.run(notify_creator, event) is False
    assert len(notifications.sent(likes.VIDEO)) == 1
