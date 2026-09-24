"""Crash the process at a named point, once, to show what a retry does.

CRASH_AT=<point> makes the first run that reaches that point exit immediately,
skipping every cleanup path, as a killed machine would. A marker file stops the
next run crashing at the same place. `--reset` clears the markers.
"""

import os

import db


def crash_point(name: str) -> None:
    if os.environ.get("CRASH_AT") != name:
        return
    marker = db.DB_PATH.parent / "crash-markers" / name
    if marker.exists():
        return
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    print(f"💥 crashing at {name}", flush=True)
    os._exit(1)

