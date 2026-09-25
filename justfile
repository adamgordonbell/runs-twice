# Every stage serves the same API on :8000, so run one stage at a time.

# the client: `just click`, `just click --lose-first-response`, `just click --user bob`, `just click --show`
click *ARGS:
    uv run client/client.py {{ARGS}}

# stage 1: a like is +1
add:
    cd src/1-add && uv run server.py --reset

# stage 2: a like is state. `FAIL_RATE=1 just set` to lose the notification
set *ARGS:
    cd src/2-set && uv run server.py {{ARGS}}

# stage 3: server + one worker. Start the server first
hand-rolled-server *ARGS:
    cd src/3-hand-rolled && uv run server.py {{ARGS}}

# stage 3 worker. Env: FAIL_RATE=0.5
hand-rolled-worker:
    cd src/3-hand-rolled && uv run worker.py

# stage 4: Temporal server + Web UI at http://localhost:8233
dev-server:
    temporal server start-dev --ui-port 8233

temporal-server *ARGS:
    cd src/4-temporal && uv run server.py {{ARGS}}

# stage 4 worker. Env: FAIL_RATE=0.5, COUNT_MODE=add
temporal-worker:
    cd src/4-temporal && uv run worker.py

test:
    cd src/1-add && uv run pytest -q
    cd src/2-set && uv run pytest -q
    cd src/3-hand-rolled && uv run pytest -q
    cd src/4-temporal && uv run pytest -q
