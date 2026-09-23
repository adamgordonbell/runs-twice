"""What happens if this runs twice?"""

import pytest

import db
import naive


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "likes.db")
    db.reset()


def test_add_twice_counts_twice():
    with db.connect() as conn:
        naive.click_like(naive.like_add, conn)
        assert db.like_count(conn) == 1206


def test_set_twice_counts_once():
    with db.connect() as conn:
        naive.click_like(naive.like_set, conn)
        assert db.like_count(conn) == 1205
