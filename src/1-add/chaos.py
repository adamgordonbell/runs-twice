"""Injected crashes: FAIL_RATE=0.3 fails each point 30% of the time; tests use fail_once(point)."""

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
