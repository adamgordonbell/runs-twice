# What happens if this runs twice? Each stage is standalone in src/.

# stage 1: a like is +1, and the retry counts it twice
add:
    cd src/1-add && uv run like.py

# stage 2: a like is state, and the retry is harmless
set:
    cd src/2-set && uv run like.py

# stage 3: the downstream work, made safe by hand. e.g. `CRASH_AT=after-notify just hand-rolled`, then `just hand-rolled --process`
hand-rolled *ARGS:
    cd src/3-hand-rolled && uv run hand_rolled.py {{ARGS}}

# stage 4, terminal 1: Temporal server + Web UI at http://localhost:8233
dev-server:
    temporal server start-dev --ui-port 8233

# stage 4, terminal 2: worker. Env: CRASH_AT=before-notify|after-count-commit, COUNT_MODE=add (the unsafe activity)
worker:
    cd src/4-temporal && uv run worker.py

# stage 4, terminal 3: e.g. `just like`, `just like --retry`, `just like --user bob`
like *ARGS:
    cd src/4-temporal && uv run starter.py {{ARGS}}

reset:
    cd src/4-temporal && uv run reset.py

test:
    cd src/1-add && uv run pytest -q
    cd src/2-set && uv run pytest -q
    cd src/4-temporal && uv run pytest -q
