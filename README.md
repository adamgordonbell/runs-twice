# What happens if this runs twice?

Idempotency, without and with Temporal. Alice clicks Like once. The server records the like, updates the video's like count and notifies the creator. The response is lost, so the client retries. Every stage below does that same job; what changes is how reliably.

Each folder in `src/` is a complete, standalone server with the same API (`POST /like`, `GET /videos/{id}`). The client in `client/` never changes: retrying is the client's job, and making the retry safe is the server's.

## The stages

| Folder | What it does | But… |
|---|---|---|
| `src/1-add` | A like is `+1`, then a notification. The retry counts the like twice and notifies twice: **1206 likes, 2 notifications.** | The server can't tell a retry from a new click. |
| `src/2-set` | **Therefore** a like is state, `(alice, video-123) = LIKE`, and the count is `SET` from the reactions. It notifies only when the reaction changed. The retry changes nothing: **1205, 1 notification.** | The database and the notification service are two systems. Crash between them and the retry sees nothing to change: **1205, 0 notifications.** The creator is never told. |
| `src/3-hand-rolled` | **Therefore** the request stores the like and an event row in one transaction, and a worker does the rest: update the count, then notify. To make that safe to rerun, the worker keeps a checkmark per finished step and passes the event ID to the notification service as an idempotency key. Two lines of business logic, wrapped in bookkeeping. | Five TODOs remain: leases so two workers don't collide, taking over from a dead worker, retries with backoff, timeouts, and seeing what's stuck. The app is turning into a workflow engine. |
| `src/4-temporal` | **Therefore** let Temporal do the bookkeeping and the five TODOs. The two steps become two activities, and the workflow is two lines. | Temporal can't see inside an activity either. **Therefore** activities must still be safe to run twice. |

Idempotency makes retries safe. Temporal makes them manageable.

### From stage 3 to stage 4

| Stage 3, by hand | Stage 4, Temporal |
|---|---|
| `server.py` stores the like and an event row | `server.py` stores the like and calls `start_workflow` |
| event ID from the like | workflow ID from the like |
| `worker.py`: `step_done` / `mark_done` around each step | `workflows.py`: `execute_activity` for each step; Temporal records the history |
| the steps, inline in `process()` | `activities.py` |
| five TODOs | leases, takeover, retries, timeouts and the Web UI, built in |

```bash
diff src/1-add/server.py src/2-set/server.py     # +1 becomes state
diff src/2-set/server.py src/3-hand-rolled/server.py   # the event row, in the same transaction
cat src/3-hand-rolled/worker.py                  # the steps, by hand
cat src/4-temporal/workflows.py                  # the same steps, with Temporal
```

## Run it

Needs [uv](https://docs.astral.sh/uv/), the [Temporal CLI](https://docs.temporal.io/cli) for stage 4, and optionally [just](https://github.com/casey/just) (see `justfile` for the one-line equivalents). All stages listen on port 8000, so run one at a time. `--reset` puts the video back to 1204 likes; start workers after it, since it replaces the database file.

```bash
cd src/1-add && uv run server.py --reset                       # or src/2-set
uv run client/client.py --lose-first-response                  # from the repo root, in a second terminal
```

Or open http://localhost:8000 for a Like button that retries the same way.

Stage 3:

```bash
cd src/3-hand-rolled
uv run server.py --reset          # terminal 1
uv run worker.py                  # terminal 2
```

Stage 4:

```bash
temporal server start-dev --ui-port 8233   # terminal 1, UI at http://localhost:8233
cd src/4-temporal
uv run server.py --reset                   # terminal 2
uv run worker.py                           # terminal 3
```

In both, `uv run client/client.py --lose-first-response --wait 2` from the repo root likes the video and prints the result once the worker has run. The workflow ID comes from the like (`like-alice-video-123`), so after a reset use `--user bob`, or restart the Temporal dev server.

## Crash it

`CRASH_AT=<point>` makes the process exit hard the first time it reaches that point, as a killed machine would. Restart it without `CRASH_AT` (keep `COUNT_MODE` if you set it) and the client's retry, or the next worker, carries on.

| Where | Command | Stage 2 | Stage 3 | Stage 4 |
|---|---|---|---|---|
| Server, after saving the like | `CRASH_AT=after-commit uv run server.py --reset` | 0 notifications | 1 | 1 |
| Worker, between the two steps | `CRASH_AT=before-notify uv run worker.py` | | The rerun skips the count | The next worker runs only `notify_creator` |
| Worker, after sending the notification | `CRASH_AT=after-notify uv run worker.py` (stage 3) | | The rerun sends again; the service ignores the repeat | |
| Worker, after the count commits, `+1` | `COUNT_MODE=add CRASH_AT=after-count-commit uv run worker.py` | | | 1206 |
| The same, with `SET` | `CRASH_AT=after-count-commit uv run worker.py` | | | 1205 |

The last two rows are the point. Stage 3 could commit the count and its checkmark in one transaction. Temporal records progress in its own service, so it can't share your database's transaction, and it can't know whether an activity's side effect landed before the worker died. So each step must be safe to run twice: `SET` a result rather than add to it, or pass a stable ID the other system can use to recognize a repeat, as `notify_creator` does.

## What Temporal gives you, and what you still add

| Temporal gives you | You still add |
|---|---|
| A durable record of which steps finished | Activities that are safe to repeat |
| Retries with backoff, and timeouts | A stable ID for the work (here, the workflow ID) |
| Taking over from a dead worker | An idempotency key for systems outside your database |
| At most one workflow per ID | |

## Tests

```bash
just test   # or `uv run pytest -q` in each src/ folder
```

Each test runs something twice, or kills it halfway, and checks the result.
