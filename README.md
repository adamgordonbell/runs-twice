# What happens if this runs twice?

Idempotency, without and with Temporal, as three small Python programs. Alice clicks Like once. The server does the work, the response is lost, and the client retries. Each stage asks the same question: what happens if this runs twice?

| Stage | File | What it shows |
|---|---|---|
| 1. Naive | `naive.py` | `+1` run twice counts the like twice. Storing the like as state, `(alice, video-123) = LIKE`, and `SET`ting the count from it does not. |
| 2. Hand-rolled | `hand_rolled.py` | The like causes more work: update the count, notify the creator. Making that safe to retry by hand means stable event IDs, a table of finished steps, and a list of TODOs that add up to a workflow engine. |
| 3. Temporal | `workflows.py`, `activities.py`, `worker.py`, `starter.py` | Temporal records each finished step, retries failures and resumes on another worker. The activities still have to be safe to run twice. |

## Run it

Needs [uv](https://docs.astral.sh/uv/), the [Temporal CLI](https://docs.temporal.io/cli) and optionally [just](https://github.com/casey/just) (each recipe is one command; see `justfile`).

```bash
uv run naive.py
uv run hand_rolled.py
```

The Temporal stage uses three terminals:

```bash
temporal server start-dev --ui-port 8233   # 1: server, UI at http://localhost:8233
uv run worker.py                           # 2: worker
uv run starter.py --retry                  # 3: Alice likes the video; the client sends the request twice
```

`uv run reset.py` puts the video back to 1204 likes. The workflow ID comes from the like (`like-alice-video-123`), so a second like from the same user is refused as a duplicate even after a reset. Use `--user bob` for a fresh run, or restart the dev server.

## Crash it

`CRASH_AT=<point>` makes the worker exit hard the first time it reaches that point, as a killed machine would. Start a second `uv run worker.py` (without `CRASH_AT`) and it picks up the work.

| Command in terminal 2 | What happens |
|---|---|
| `CRASH_AT=before-notify uv run worker.py` | The worker dies between the two steps. The new worker runs `notify_creator` only: Temporal already recorded that `update_like_count` finished. |
| `COUNT_MODE=add CRASH_AT=after-count-commit uv run worker.py` | The count update commits, then the worker dies before Temporal hears about it. Temporal retries the activity (attempt 2) and the `+1` runs again: 1206 likes. |
| `CRASH_AT=after-count-commit uv run worker.py` | Same crash, but the activity `SET`s the count from the reactions: the retry leaves 1205. |

The last two rows are the point. Temporal remembers progress and retries for you, but it can't know whether an activity's side effect landed before the worker died. So each activity must be safe to run twice: `SET` a result rather than add to it, or pass a stable ID the other system can use to recognize a repeat (as `notify_creator` does).

## What Temporal gives you, and what you still add

| Temporal gives you | You still add |
|---|---|
| A durable record of which steps finished | Activities that are safe to repeat |
| Retries with backoff, and timeouts | A stable ID for the work (here, the workflow ID) |
| Resuming on another worker after a crash | An idempotency key for systems outside your database |
| At most one running workflow per ID | |

## Tests

```bash
uv run pytest -q
```

Each test runs an operation twice and checks the result, including the two activities under Temporal's `ActivityEnvironment`.
