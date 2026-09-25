# What happens if this runs twice?

Alice clicks Like. The server records the like, bumps the video's like count and notifies the creator. The response gets lost on the way back, so the client retries. Every stage in `src/` does that same job; what changes is how safely it survives the retry.

Each folder in `src/` is a complete server with the same API (`POST /like`, `GET /videos/{id}`). The client in `client/` never changes. Retrying is the client's job; making the retry safe is the server's.

## The stages

`src/1-add` treats a like as `+1`, then sends a notification. The retry counts it again and notifies again: 1206 likes, 2 notifications. The server can't tell a retry from a new click.

`src/2-set` stores the like as state, `(alice, video-123) = LIKE`, and sets the count from the reactions. It notifies only when the reaction actually changed, so the retry does nothing: 1205, 1 notification. But the database and the notification service are two systems. Crash between them and the retry sees nothing to change: 1205, 0 notifications. The creator never hears about it.

`src/3-hand-rolled` stores the like and an event row in one transaction, and a worker does the rest: update the count, then notify. To make the worker safe to rerun, it keeps a checkmark per finished step and passes the event ID to the notification service as an idempotency key. A worker claims an event before working on it; if it goes quiet for 30 seconds, another worker takes over. That's two lines of business logic wrapped in bookkeeping, and quiet isn't dead: a slow worker and its replacement can both run a step, so the steps have to be idempotent anyway. Three TODOs are still open in `worker.py`: retries with backoff, timeouts on hung calls, and some way to see what's stuck. It's turning into a workflow engine.

`src/4-temporal` lets Temporal do the bookkeeping, the takeover and the three TODOs. The server starts a workflow whose ID comes from the like. Recording the like, updating the count and notifying are three activities, and the workflow is three lines. Temporal can't see inside an activity either, though, so the activities still have to be safe to run twice.

Idempotency makes retries safe. Temporal makes them manageable.

To see the changes between stages:

```bash
diff src/1-add/server.py src/2-set/server.py            # +1 becomes state
diff src/2-set/server.py src/3-hand-rolled/server.py    # the event row, in the same transaction
cat src/3-hand-rolled/worker.py                         # the steps, by hand
cat src/4-temporal/workflows.py                         # the same steps, with Temporal
```

## Running it

You need [uv](https://docs.astral.sh/uv/), the [Temporal CLI](https://docs.temporal.io/cli) for stage 4, and optionally [just](https://github.com/casey/just) (the `justfile` has the one-line equivalents). Every stage listens on port 8000, so run one at a time. `--reset` puts the video back at 1204 likes by replacing the database file, so start workers after it.

Stages 1 and 2:

```bash
cd src/1-add && uv run server.py --reset          # or src/2-set
uv run client/client.py --lose-first-response     # from the repo root, in a second terminal
```

Or open http://localhost:8000 for a Like button. It shows the like right away, retries in the background the same way the CLI does, and polls `GET /videos/video-123?user=alice` to see whether the server has recorded it yet. Add `?user=bob` to the page URL to switch user.

Stage 3:

```bash
cd src/3-hand-rolled
uv run server.py --reset          # terminal 1
uv run worker.py                  # terminal 2
uv run worker.py                  # terminal 3, optional: they share the events
```

Stage 4:

```bash
temporal server start-dev --ui-port 8233   # terminal 1, UI at http://localhost:8233
cd src/4-temporal
uv run server.py --reset                   # terminal 2
uv run worker.py                           # terminal 3
```

For stages 3 and 4, `uv run client/client.py --lose-first-response --wait 2` from the repo root likes the video and prints the result once the worker has run. The workflow ID comes from the like (`like-alice-video-123`), so after a reset either use `--user bob` or restart the Temporal dev server.

## Making it fail

`FAIL_RATE=<0..1>` makes each failure point in the code raise with that probability, as if the process died right there. The client retries a failed request; a failed worker step gets retried on the next pass (stage 3) or by Temporal (stage 4).

```bash
FAIL_RATE=1 uv run server.py --reset            # stage 2: every request fails after the commit
FAIL_RATE=0.5 uv run worker.py                  # stage 3 or 4: steps fail half the time
COUNT_MODE=add FAIL_RATE=0.5 uv run worker.py   # stage 4, counting with +1 instead of SET
```

The failure points, and what a failure at each one shows:

- `before-response` (stage 1): the like counted, the client retries, it counts again.
- `after-commit` (stage 2): saved but not notified, and the retry sees nothing changed, so no notification, ever.
- `after-commit` (stage 3): saved with its event row, so the worker still notifies.
- `before-notify` (stage 3): the rerun skips the count (already checked off) and sends.
- `after-notify` (stages 3 and 4): sent but not recorded as sent; the rerun sends again and the service ignores the repeated key.
- `after-count-commit` (stage 4): Temporal retries the count. `SET` gives the same answer; `COUNT_MODE=add` counts the like twice.

That last one is the whole point. Stage 3 could commit the count and its checkmark in one transaction. Temporal keeps its record of progress in its own service, so it can't share your database's transaction, and it can't know whether an activity's side effect landed before the worker died. Each step has to be safe to run twice: set a result rather than add to it, or pass a stable ID the other system can use to recognize a repeat, the way `notify_creator` does.

For a real crash, Ctrl-C a worker mid-run and start another. The new one picks up where the history says, in about two seconds (`sticky_queue_schedule_to_start_timeout` in `worker.py`).

A workflow that's still retrying when you `--reset` will finish into the fresh database, so stop the worker or let it drain before resetting.

## Tests

```bash
just test   # or `uv run pytest -q` in each src/ folder
```

Each test runs something twice, or fails it halfway with `chaos.fail_once(point)`, and checks the result. `fail_once` fails the next pass through that point, so the tests are deterministic with `FAIL_RATE` unset.
