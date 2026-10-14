# 0003 — Celery for background data loads

- **Status:** Accepted
- **Date:** 2026-10-14

## Context

The first plan ran the ETL as a one-shot Docker Compose service. That works
for a single Ohio load, but it does not fit where the project is going:

- Loading a new state or filing period should not need a redeploy.
- A load of millions of rows takes minutes. It should not block a web request.
- Each load should leave a record: what was loaded, when, how many rows, and
  why it failed if it did.

## Decision

Data loads run as **Celery** tasks, with **Redis** as the message broker.

- A **worker** service runs alongside the Django service in Docker Compose,
  from the same backend image.
- Each load is recorded in a **`LoadRun`** model: source file, status, row
  counts, timings and any error. Celery's own result backend is not used for
  this; the record lives in the application's database, where the admin and
  the API can see it.
- Loads can be started from the **Django admin** or with a **management
  command**. The command can also run a load in the foreground, which keeps
  local debugging simple.
- A load runs inside a **transaction**: a failed load leaves the database as
  it was.

Implementation is tracked in
[#15](https://github.com/ShawnMcCollum/BroadbandMap/issues/15).

## Alternatives considered

- **One-shot Compose service** (the original plan). The simplest option, but
  it has no way to start loads on demand and no record of past loads.
- **Django management command only.** Simple, but long loads tie up a
  terminal, and nothing tracks progress for other users.
- **A lighter queue (RQ, Dramatiq, Huey).** Each would work. Celery is the
  most widely used with Django and has the deepest integration and
  documentation.

## Consequences

- **Positive:** Loads are on demand, tracked and repeatable. The same pattern
  extends to scheduled refreshes (Celery Beat) when new FCC releases appear.
- **Negative:** Two more services (Redis and the worker) to run, and task
  failures need care: retries, timeouts, and idempotent loads.
- **Supersedes:** running the ETL as a Compose service (#8, open question 9).
  Reviewers still need only Docker.
