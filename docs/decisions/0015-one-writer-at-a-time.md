# 0015 — One writer of the loaded tables at a time

- **Status:** Accepted
- **Date:** 2026-10-16

## Context

Three commands write the tables the loader owns: a data load
(`load_served_unserved`, [0013](0013-release-scoped-data-loads.md)), a rollup
rebuild (`build_rollups`) and a release's deletion (`delete_release`,
[#55](https://github.com/ShawnMcCollum/BroadbandMap/issues/55)). Until now,
nothing stopped two of them from running at once. The data-layer review
([#38](https://github.com/ShawnMcCollum/BroadbandMap/issues/38), finding M4)
and [#45](https://github.com/ShawnMcCollum/BroadbandMap/issues/45) list what
happens then:

- Two loads of the same release, or two first loads for a state, both run for
  minutes. Then the second fails on a unique key, with a raw `IntegrityError`
  or a `LoadError` from its `COPY`.
- A rollup rebuild, or a deletion, of a release that a load is replacing works
  on rows the load is about to delete.
- Two loads of different releases both commit, but they do not run side by
  side. The second waits at its `ANALYZE` until the first commits, and the
  first's vacuum ([0014](0014-vacuum-after-each-data-load.md)) can then wait
  for the second.

Background loads ([#15](https://github.com/ShawnMcCollum/BroadbandMap/issues/15))
make two writers at once likely. Since 0013, no writer takes a lock that blocks
a reader, and a guard against two writers must not bring one back.

## Decision

1. **One lock for every writer of the loaded tables.** A data load, a rollup
   rebuild and a deletion each take it before they read or write those tables,
   so no two of them run at once, whichever releases they touch.
2. **A PostgreSQL transaction-level advisory lock, tried, never waited for**
   (`pg_try_advisory_xact_lock`). It is taken first in the writer's transaction.
   PostgreSQL releases it when the transaction commits or rolls back, and when
   the process dies. It locks no table, so no reader waits for it.
   - A data load takes it before it reads the database or checks its files. The
     checks that read the database run in the load's transaction, so nothing
     they read can change before the commit.
   - A deletion takes it once its confirmation question is answered, so no lock
     is held while waiting for an answer.
   - A rebuild of every release takes it in each release's transaction, and
     reads the release again by its dates under it.
   - The vacuum after the commit (0014) runs outside it, since `VACUUM` cannot
     run inside a transaction.
3. **One key:** the eight bytes `bbmwrite` read as a big-endian integer,
   7089349123222631525. `pg_locks` shows it as classid 1650617719, objid
   1919513701, objsubid 1. Nothing else in the database takes advisory locks.
4. **The holder says what it is doing, and nothing is stored.** Before trying
   the lock, a writer sets its transaction's `application_name` to what it does:
   `load of June 2025 (processed 2026-10-01)`, `rollup rebuild of …` or
   `deletion of …`. PostgreSQL restores the name when the transaction ends.
5. **A second writer stops at once and names the first,** read from `pg_locks`
   and `pg_stat_activity`, and changes nothing: `another writer is running:
   load of June 2025 (processed 2026-10-01), process 51104, since 2026-10-16
   03:46:17 UTC; try again once it has finished`. `load_served_unserved()`
   raises `WriteLockHeld`, not a `LoadError`, so a caller can tell a busy
   database from bad files. The commands exit with a `CommandError`.

## Measurements

On a copy of the development database holding December 2025 (D25) and June
2025 (J25): PostgreSQL 17.5, as in 0013. These are single runs.

**Two loads of different releases at once, without the lock:** replaces of
D25 and J25, started 2 s apart.

| Step | J25 | D25 |
|---|---|---|
| Statuses (`COPY`) | 74 s | 82 s |
| Waiting at `ANALYZE` for the other to commit | — | 81 s |
| Load, in all | 168 s | 253 s |
| Vacuum after the commit | 95 s, 83 s of it waiting for D25 to commit | 17 s |

Both had finished 275 s after the first started. One after the other, the same
two replaces take about 320 s.

**With the lock:**

- A replace of J25 took 153 s, and its vacuum 8 s, as without the lock.
- While it ran, the database held one advisory lock, by the load's process,
  named `load of June 2025 (processed 2026-10-01)`, and no `ACCESS EXCLUSIVE`
  lock. A reader of D25's county rollups, waiting at most one second for a
  lock, took 2.3 ms.
- A rollup rebuild, a deletion of D25 and a replace of D25, each started during
  the load, stopped 134 ms, 51 ms and 88 ms after being called, naming the
  load. With Django's start-up, each command took 2.3 to 2.4 s in all.
- A deletion started during a rollup rebuild stopped, naming
  `rollup rebuild of June 2025 (processed 2026-10-01)`.
- Being refused the lock took 0.4 ms, and reading who holds it 2.4 ms.

## Alternatives considered

- **One lock per release, and one per state's boundaries.** Two loads of
  different releases could then run at once. Measured above, that saved about
  45 s of 320 s, and the first command returned 95 s later than it would have
  alone. It needs a key per release, a boundary lock that every load takes
  first, and one lock per release for a rebuild of every release.
- **Waiting for the lock** (`pg_advisory_xact_lock`, with or without a
  `lock_timeout`). A second command would sit silent for up to seven minutes
  behind a first load. A scheduler that wants to wait can retry.
- **A session-level advisory lock** (`pg_try_advisory_lock`). It outlives a
  rolled-back transaction until it is unlocked, so a connection that a Celery
  worker reuses after an error could keep it.
- **A lock on a table or a row** (`LOCK TABLE … NOWAIT`, or
  `SELECT … FOR UPDATE NOWAIT` on a row of its own). A table lock mode that
  excludes other writers also conflicts with vacuums; a row needs a table and
  a migration. Neither names its holder.
- **Recording the running writer in a table**, such as the load record of #15.
  A row written in the writer's transaction is invisible to others until it
  commits, and a row written outside it must be cleaned up after a crash.

## Consequences

- **Positive:** No two writers of the loaded tables run at once. The second
  stops within a second, changes nothing, and names the first, its process id
  and when it started.
- **Positive:** No reader waits for the guard: an advisory lock locks no table.
- **Positive:** A crash leaves no lock and no record to clean up.
- **Negative:** Two loads of different releases no longer overlap. The second
  is started again once the first has finished, about two and a half minutes
  later.
- **Negative:** A rebuild of every release lets the lock go between releases. A
  writer that starts in between stops the rebuild before its next release; the
  releases before it stay rebuilt.
- **Negative:** Only writers that take the lock are kept out. Hand-run SQL, or a
  migration that changes the loaded tables, is not.
- **Negative:** A writer that hangs keeps the lock until its connection ends. The
  refusal gives its process id, which `pg_terminate_backend()` can end.
- **Follow-up:** The Celery task of #15 calls `load_served_unserved()`, which
  takes the lock, and treats `WriteLockHeld` as "try again later".
