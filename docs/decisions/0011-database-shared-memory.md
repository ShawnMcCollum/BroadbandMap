# 0011 — Shared memory for the database container

- **Status:** Accepted
- **Date:** 2026-10-15

## Context

PostgreSQL runs large queries in parallel. The leader process and its workers
share hash tables and other state through *dynamic shared memory*. The
`postgis/postgis` image keeps PostgreSQL's default,
`dynamic_shared_memory_type = posix`, which creates that memory as files in
`/dev/shm`. Docker gives each container a 64 MB `/dev/shm` unless the service
sets another size, and the `db` service did not.

When a parallel query needs more shared memory than `/dev/shm` has left, it
fails:

```text
ERROR:  could not resize shared memory segment "/PostgreSQL.…" to 16777216 bytes: No space left on device
```

[0010](0010-place-and-county-subdivision-rollups.md) met this error while
profiling a design it then dropped, and left raising the limit as a follow-up
([#36](https://github.com/ShawnMcCollum/BroadbandMap/issues/36)). The API
([#3](https://github.com/ShawnMcCollum/BroadbandMap/issues/3)), the drill-down
([#26](https://github.com/ShawnMcCollum/BroadbandMap/issues/26)) and background
loads ([#15](https://github.com/ShawnMcCollum/BroadbandMap/issues/15)) will run
large queries while others are running.

**The database container before this change:**

| Setting | Value |
|---|---|
| `/dev/shm` | 64 MB |
| `dynamic_shared_memory_type` | `posix` |
| `shared_buffers` | 128 MB |
| `work_mem` | 4 MB |
| `hash_mem_multiplier` | 2 |
| `max_parallel_workers_per_gather` | 2 |
| `max_parallel_workers` | 8 |

- PostgreSQL's main shared memory, `shared_buffers` included, is not in
  `/dev/shm`. An idle server uses 1.0 MB of it.
- A parallel hash join sizes its shared hash table to fit `work_mem` ×
  `hash_mem_multiplier` for each process: 24 MB for a leader and two workers at
  these settings. A larger input is split into batches on disk. So a query's
  shared memory depends on how many hash joins it runs at once, and on these
  settings, much more than on the size of the data.

**One query at a time,** on the December 2025 Ohio data (4,542,350 statuses):

| Query | Hash tables | Peak `/dev/shm` use |
|---|---|---|
| County-subdivision rollup `GROUP BY`, as `build_rollups` runs it | 21.0 MB; 4.9 MB in 64 batches | 48.4 MB |
| 0010's dropped design: the same grouping through a separate assignment table | 16.7 MB; 20.9 MB; 4.9 MB in 64 batches | 46.4 MB |

- The dropped design's query failed twice in 0010's profiling. The data has
  been reloaded since, and the query now completes alone.
- Every query in a data load and in the full-data suite runs within 64 MB, one
  at a time.

**Several queries at once.** Copies of the county-subdivision rollup query,
started together:

| `/dev/shm` | 2 at once | 3 at once | 4 at once | 5 at once |
|---|---|---|---|---|
| 64 MB | both fail | – | – | – |
| 128 MB | run, peak 95.8 MB | 2 of 3 fail | 3 of 4 fail | 2 of 5 fail |
| 256 MB | run, peak 95.8 MB | run, peak 143.2 MB | run, peak 174.6 MB | run, peak 206.0 MB |

- At 64 MB, two rollup queries at once are enough for both to fail.
- The peaks are below the sum of single runs, because the copies do not reach
  their peaks at the same moment.

## Decision

1. **The `db` service sets `shm_size: 256mb`** in `docker-compose.yml`, with a
   comment that points here.
   - Five copies of the heaviest rollup query ran at once within it, peaking at
     206 MB.
   - It is the size the PostgreSQL image's documentation suggests for this
     error.
   - It is a limit, not a reservation. `/dev/shm` is a `tmpfs`, which holds
     memory only for the segments in use, and PostgreSQL removes a query's
     segments when the query ends.
2. **The size is fixed in `docker-compose.yml`,** not read from `.env`. Unlike
   the host ports, nothing about a reviewer's machine calls for a different
   value.
3. **PostgreSQL's own settings keep the image's defaults.** Tuning `work_mem`,
   `shared_buffers` or the number of parallel workers is a separate decision.

## Measurements

- `/dev/shm` use was read with `df` inside the container every 10 ms while each
  query ran.
- Concurrent copies were started at the same instant with `pg_sleep_until`,
  each in its own session.
- The 128 MB and 256 MB runs used a temporary container from the same image on
  the same data volume, with the `db` service stopped.
- The dropped design's query ran in a transaction that was rolled back. Every
  other query only read.
- With parallel query off (`max_parallel_workers_per_gather = 0`), the
  county-subdivision rollup took 6.8–8.1 s, against 3.0–3.5 s in parallel,
  both with the data cached.

## Alternatives considered

- **Keep 64 MB.** Two rollup queries at once fail.
- **128 MB.** Two run at once; a third fails.
- **512 MB or more.** No measured query needs it. A larger limit changes only
  how much memory a runaway workload could hold before it fails.
- **Turning parallel query off.** Queries then use no dynamic shared memory, but
  the county-subdivision rollup takes about twice as long.
- **`min_dynamic_shared_memory`.** Reserves the space inside PostgreSQL's main
  shared memory at startup, outside `/dev/shm`. It holds that memory for as long
  as the server runs, and needs a custom server command in Compose.
- **Another `dynamic_shared_memory_type`.** `sysv` would bypass `/dev/shm`.
  `mmap` puts the segments in the data directory, which PostgreSQL's
  documentation discourages. Both leave the image's documented setup for a
  problem that `shm_size` solves.

## Consequences

- **Positive:** Up to five of the project's heaviest queries run at once. The
  API, the dashboard and background loads can query the database side by side.
- **Positive:** The memory is used only while a query needs it.
- **Negative:** A `db` container created before this change keeps 64 MB until
  Compose recreates it. The next `docker compose up` or `docker compose run`
  does so, and keeps the data in the `pgdata` volume.
- **Negative:** The size was measured at the image's default `work_mem`,
  `hash_mem_multiplier` and parallel workers. Raising any of them raises what
  each parallel query uses, and the size should be measured again.
