# 0014 — Vacuum and analyze after each data load

- **Status:** Accepted
- **Date:** 2026-10-15

## Context

[0013](0013-release-scoped-data-loads.md) makes a data load add one release
beside those already loaded. A load no longer starts with a `TRUNCATE`, which
used to discard whatever the previous load left behind. Since then:

- A replace (`--replace`) deletes the release's 4.5 million statuses and about
  379,000 rollups inside the load's transaction, and `build_rollups` deletes
  and recreates every release's rollups. The old rows stay in their tables as
  dead rows until a vacuum frees their space for new rows.
- A load analyzes the statuses, and the census blocks when it loads them,
  inside its transaction, so that the rollups are built with statistics on
  the new release (0013, decision 9). Nothing analyzes the rollups, which the
  API ([#3](https://github.com/ShawnMcCollum/BroadbandMap/issues/3)) will read.
- Until a vacuum, the pages that hold a load's new rows are not marked
  all-visible, so an index-only scan of them still reads the table.

0013 left vacuuming to
[#42](https://github.com/ShawnMcCollum/BroadbandMap/issues/42).

PostgreSQL's autovacuum does this work in the background. On the development
database, with the server running throughout, it finished within about 70 s of
each write (see Measurements). But it acts on counters the server keeps in
memory, which are reset when the server does not shut down cleanly: the
data-layer review ([#38](https://github.com/ShawnMcCollum/BroadbandMap/issues/38))
found them all at zero after a container was recreated, and autovacuum then had
nothing to act on. It also throttles itself, and never reached the release and
state tables, whose few rows stay below its thresholds.

## Decision

1. **After a data load commits, the `load_served_unserved` command vacuums and
   analyzes the ten tables the loader owns** (`LOADER_MODELS`), in one
   `VACUUM (ANALYZE, TRUNCATE false)` statement, and prints how long it took.
   `build_rollups` does the same for the rollups, after rebuilding every
   release.
2. **The loader function, `etl.load.load_served_unserved()`, does not vacuum.**
   It stays one transaction, after which an exception still means that nothing
   changed. A vacuum runs after the commit, so a vacuum error raised from inside
   the function would report a committed load as failed. Another caller, such
   as a background task
   ([#15](https://github.com/ShawnMcCollum/BroadbandMap/issues/15)), vacuums the
   same way once the load returns.
3. **Every loader table, after every load.** A load that finds its state's
   boundaries loaded does not write the seven boundary tables, but vacuuming
   and analyzing them takes about a second, and one list stays right as
   `LOADER_MODELS` changes.
4. **`TRUNCATE false`.** Without it, a vacuum that finds empty pages at the end
   of a table takes an `ACCESS EXCLUSIVE` lock to cut them off, and readers
   would wait for it. With it, no step of a load takes a lock that blocks a
   reader (0013). Space freed at the end of a table is reused by the next load
   instead of being returned to the operating system. Autovacuum keeps
   PostgreSQL's default.
5. **The analyze inside the load's transaction stays.** The rollups are built
   from the new release's statuses before the load commits, and need their
   statistics then.
6. **Inside a transaction block, where `VACUUM` cannot run, nothing is done.**
   Only the test suite runs the commands inside one.
7. **A failed load is not vacuumed.** Autovacuum frees the rows its
   rolled-back `COPY` wrote.

## Measurements

PostgreSQL 17.5 with its default settings for vacuuming (`maintenance_work_mem`
64 MB, autovacuum naptime 60 s and cost delay 2 ms).

**Autovacuum, on the development database** (times in UTC):

| Write, and when it committed | Dead rows | Autovacuum finished |
|---|---|---|
| Delete of June 2025 (J25), 01:26:48 | 4,552,967 statuses | 01:28:04, 76 s later |
| `build_rollups` of two releases, 01:30:56 | 757,792 rollups | 01:32:04, 68 s later; analyzed 01:32:05 |

**`VACUUM (ANALYZE, TRUNCATE false)`, one table at a time, on the development
database** with two releases loaded:

| Table | After replacing D25 | With nothing to do |
|---|---|---|
| Statuses | 5.1 s: 4,542,350 dead rows, one pass over its five indexes | 0.7 s |
| Rollups | 0.5 s: 378,741 dead rows | 0.3 s |
| Release | 2 ms | |
| Census blocks | | 1.0 s, of which 0.8 s analyzing |
| The six other boundary tables | | 0.3 s |

- Right after the replace, 51,737 of the statuses' 155,024 pages were marked
  all-visible; after the vacuum, 154,976.
- No vacuum truncated a table. Each load's `COPY` filled space freed by the
  vacuum before it: the statuses stayed at 1,211 MB through a replace, a delete
  and a new load.

**The commands, end to end** on a new, empty database:

| Command | Command's own time | Vacuum and analyze, after it |
|---|---|---|
| First load, D25 with the census boundaries | 436 s | 3 s, ten tables |
| New release, J25 beside D25 | 151 s | 2 s, ten tables |
| Replace of D25 | 149 s | 6 s, ten tables |
| `build_rollups`, both releases | — | under 1 s (`0 s`), the rollups |

- After each command, every one of the ten tables had no dead rows and had
  been analyzed after its vacuum.
- A replace needs room for the release twice until it commits. On the new
  database the replace grew the statuses from 808 MB to 1,211 MB; the vacuum
  then freed 404 MB for the next load to reuse, as on the development
  database.

## Alternatives considered

- **Leave it to autovacuum.** It runs within about 70 s on a server that keeps
  running, but not while its counters are lost, never on the smallest tables,
  and until it runs the rollups keep the statistics from before the load.
- **Vacuum inside `load_served_unserved()`.** Every caller would get it, but a
  vacuum error after the commit would report a committed load as failed.
- **Only the tables a load wrote.** About a second faster per load, for a
  second list of tables to keep in step with `LOADER_MODELS`.
- **The default `TRUNCATE`.** PostgreSQL takes the truncation lock only when no
  one holds a conflicting lock, and gives it up when a reader starts waiting,
  so readers would wait milliseconds. It would still be the one
  `ACCESS EXCLUSIVE` lock in a load.
- **`vacuum_truncate = false` on each table.** It would stop autovacuum from
  truncating too: a migration of storage parameters for a lock that autovacuum
  already gives up when a reader waits.
- **`VACUUM FULL`.** It returns all free space to the operating system, but
  rewrites each table under an `ACCESS EXCLUSIVE` lock.
- **Tuning autovacuum** (naptime, cost delay, thresholds). Its defaults kept
  up with every write measured here; what they cannot do is run before the
  command returns, or after the counters are lost.

## Consequences

- **Positive:** When a data load or `build_rollups` ends, its tables hold no
  dead rows, the pages of new rows are all-visible, and every table's
  statistics, the rollups' included, describe the releases now loaded.
- **Positive:** A replace's space is free for the next load as soon as the
  command ends.
- **Negative:** Each data load takes 2 to 6 s longer, and `build_rollups` up
  to a second.
- **Negative:** Callers of `load_served_unserved()` other than the command must
  vacuum themselves.
- **Negative:** The command's vacuum never shrinks a table's files. Only
  autovacuum or a `VACUUM FULL` returns space to the operating system.
