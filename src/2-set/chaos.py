"""Things fail. FAIL_RATE=0.3 makes each failure point raise 30% of the time.

A failure point sits right after a side effect has landed (a commit, a sent
notification) and before anyone has heard about it, which is exactly when a
retry has to be safe. To kill a process outright instead, Ctrl-C a worker.

Tests use fail_once(point) to make the next pass through a point fail.
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
