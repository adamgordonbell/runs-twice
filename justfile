# What happens if this runs twice? Three terminals for the Temporal stage: dev-server, worker, like.

# stage 1: +1 vs SET, no Temporal
naive:
    uv run naive.py

# stage 2: hand-rolled event IDs and step tracking. e.g. `CRASH_AT=after-notify just hand-rolled`, then `just hand-rolled --process`
hand-rolled *ARGS:
    uv run hand_rolled.py {{ARGS}}

# terminal 1: Temporal server + Web UI at http://localhost:8233
dev-server:
    temporal server start-dev --ui-port 8233

# terminal 2: worker. Env: CRASH_AT=before-notify|after-count-commit, COUNT_MODE=add (the unsafe activity)
worker:
    uv run worker.py

# terminal 3: e.g. `just like`, `just like --retry`, `just like --user bob`
like *ARGS:
    uv run starter.py {{ARGS}}

reset:
    uv run reset.py

test:
    uv run pytest -q
