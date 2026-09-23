"""Crash the process at a named point, once, to show what a retry does.

CRASH_AT=<point> makes the first run that reaches that point exit immediately,
skipping every cleanup path, as a killed machine would. A marker file stops the
next run crashing at the same place. `just reset` clears the markers.
"""

import os
from pathlib import Path

MARKERS = Path(".crash-markers")


def crash_point(name: str) -> None:
    if os.environ.get("CRASH_AT") != name:
        return
    marker = MARKERS / name
    if marker.exists():
        return
    MARKERS.mkdir(exist_ok=True)
    marker.touch()
    print(f"💥 crashing at {name}", flush=True)
    os._exit(1)


def clear() -> None:
    for marker in MARKERS.glob("*"):
        marker.unlink()
