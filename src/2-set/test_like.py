"""What happens if this runs twice?"""

import pytest

import db
import like


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "likes.db")
    db.reset()


def test_run_twice_counts_once():
    with db.connect() as conn:
        like.click_like(conn)
        assert db.like_count(conn) == 1205
