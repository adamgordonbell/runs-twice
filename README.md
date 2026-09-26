# What happens if this runs twice?

Alice likes a video. The server saves the like, updates the count, and notifies the creator. The response is lost on the way back, so her phone sends the like again.

In a distributed system, everything eventually runs twice. Clients retry, queues redeliver, workers restart. This repo takes one small feature through four versions. Each version survives more of those reruns, and each fix shows what the next one has to deal with. It's the code for the video *What happens if this runs twice?*

Two lessons come out of it. A step is safe to rerun when it records a fact rather than performing an action. And a workflow engine handles the retries, but it can't make your steps safe to rerun. That part is always your job.

## Contents

1. **`src/1-add`: a like is +1.** The retry counts the like twice and notifies twice.
2. **`src/2-set`: a like is a fact.** The retry changes nothing. But the database and the notification service are two systems, and a crash between them loses the notification for good.
3. **`src/3-hand-rolled`: a note and a worker.** The like and a note to finish the job commit together. A worker checks off each step and passes the note's ID to the notification service as an idempotency key. The bookkeeping grows until it's a small workflow engine with three TODOs.
4. **`src/4-temporal`: the same steps on Temporal.** The workflow is three lines. Temporal runs each step at least once, so each step still has to be safe to run twice.

Every stage serves the same API, and `client/` works with all of them. SQLite stands in for the app's database. A second SQLite file stands in for the notification service.

## Running it

You need [uv](https://docs.astral.sh/uv/), plus the [Temporal CLI](https://docs.temporal.io/cli) for stage 4. The `justfile` has a recipe for each step.

```bash
just add                              # or: just set
just click --lose-first-response      # in a second terminal
```

Stages 3 and 4 also need a worker: `just hand-rolled-server` and `just hand-rolled-worker`, or `just dev-server`, `just temporal-server` and `just temporal-worker`. Then run `just click --lose-first-response --wait 2`. A like's ID comes from the user and the video, so after a stage 4 `--reset`, either like as `--user bob` or restart the dev server. Set `FAIL_RATE=0.5` on a server or worker to make it fail at the points where a rerun matters.

`just test` runs each stage's tests. Every test runs something twice, or fails it halfway, and checks the result.
