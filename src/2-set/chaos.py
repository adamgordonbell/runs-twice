"""FAIL_RATE=0.3 makes each failure point raise 30% of the time.

Failure points sit right after a side effect lands (a commit, a sent notification)
and before anyone has heard about it, which is where a retry has to be safe.
Tests use fail_once(point) to fail the next pass through a point.
"""

import os
import random

FAIL_RATE = float(os.environ.get("FAIL_RATE", "0"))
_fail_next: set[str] = set()


class InjectedFailure(Exception):
    pass


def fail_once(point: str) -> None:
    _fail_next.add(point)


def maybe_fail(point: str) -> None:
    if point in _fail_next or random.random() < FAIL_RATE:
        _fail_next.discard(point)
        print(f"💥 injected failure at {point}", flush=True)
        raise InjectedFailure(point)
