# What happens if this runs twice?

Idempotency, without and with Temporal. Alice clicks Like once. The server records the like, updates the video's like count and notifies the creator. The response is lost, so the client retries. Every stage below does that same job; what changes is how reliably.

Each folder in `src/` is a complete, standalone server with the same API (`POST /like`, `GET /videos/{id}`). The client in `client/` never changes: retrying is the client's job, and making the retry safe is the server's.

## The stages

| Folder | What it does | But… |
|---|---|---|
| `src/1-add` | A like is `+1`, then a notification. The retry counts the like twice and notifies twice: **1206 likes, 2 notifications.** | The server can't tell a retry from a new click. |
| `src/2-set` | **Therefore** a like is state, `(alice, video-123) = LIKE`, and the count is `SET` from the reactions. It notifies only when the reaction changed. The retry changes nothing: **1205, 1 notification.** | The database and the notification service are two systems. Crash between them and the retry sees nothing to change: **1205, 0 notifications.** The creator is never told. |
| `src/3-hand-rolled` | **Therefore** the request stores the like and an event row in one transaction, and a worker does the rest: update the count, then notify. To make that safe to rerun, the worker keeps a checkmark per finished step and passes the event ID to the notification service as an idempotency key. Two lines of business logic, wrapped in bookkeeping. | Five TODOs remain: leases so two workers don't collide, taking over from a dead worker, retries with backoff, timeouts, and seeing what's stuck. The app is turning into a workflow engine. |
| `src/4-temporal` | **Therefore** let Temporal do the bookkeeping and the five TODOs. The server only starts a workflow, with its ID taken from the like. Recording the like, updating the count and notifying become three activities, and the workflow is three lines. | Temporal can't see inside an activity either. **Therefore** activities must still be safe to run twice. |

Idempotency makes retries safe. Temporal makes them manageable.

### From stage 3 to stage 4

| Stage 3, by hand | Stage 4, Temporal |
|---|---|
| `server.py` stores the like and an event row | `server.py` calls `start_workflow`; the like is the workflow's first step |
| event ID from the like, `ON CONFLICT DO NOTHING` | workflow ID from the like, `REJECT_DUPLICATE` |
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

Or open http://localhost:8000 for a Like button. It shows the like straight away (optimistic), retries in the background the same way the CLI does, and polls `GET /videos/video-123?user=alice`, whose `liked` field says whether the server has recorded it yet. `?user=bob` on the page URL switches user.

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

## Make it fail

`FAIL_RATE=<0..1>` makes each failure point in the code raise with that probability, as if the process died there. The client retries a failed request; a failed worker step is retried on the next pass (stage 3) or by Temporal (stage 4).

```bash
FAIL_RATE=1 uv run server.py --reset            # stage 2: every request fails after the commit
FAIL_RATE=0.5 uv run worker.py                  # stage 3 or 4: steps fail half the time
COUNT_MODE=add FAIL_RATE=0.5 uv run worker.py   # stage 4, with the count as +1 instead of SET
```

| Point | Stage | What a failure there shows |
|---|---|---|
| `before-response` | 1 | The like counted, the client retries, it counts again: 1206, 2 notifications |
| `after-commit` | 2 | Saved, not notified; the retry sees nothing changed: 0 notifications, forever |
| `after-commit` | 3 | Saved with its event row; the worker still notifies |
| `before-notify` | 3 | The rerun skips the count (checkmark) and sends |
| `after-notify` | 3, 4 | Sent, but not recorded as sent; the rerun sends again and the service ignores the repeat key |
| `after-count-commit` | 4 | Temporal retries the count. `SET` gives the same answer; `COUNT_MODE=add` counts the like twice |

The last row is the point. Stage 3 could commit the count and its checkmark in one transaction. Temporal records progress in its own service, so it can't share your database's transaction, and it can't know whether an activity's side effect landed before the worker failed. So each step must be safe to run twice: `SET` a result rather than add to it, or pass a stable ID the other system can use to recognize a repeat, as `notify_creator` does.

For a real crash, Ctrl-C a worker mid-run and start another: the new one picks up where the history says, in about two seconds (`sticky_queue_schedule_to_start_timeout` in `worker.py`).

A workflow that is still retrying when you `--reset` will finish into the fresh database, so stop the worker (or let it drain) before resetting.

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

Each test runs something twice, or makes it fail halfway with `chaos.fail_once(point)`, and checks the result. `fail_once` fails the next pass through that point, so tests are deterministic with `FAIL_RATE` unset.
