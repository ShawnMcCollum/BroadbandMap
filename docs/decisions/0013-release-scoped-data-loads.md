# 0013 — A data load adds one release

- **Status:** Accepted
- **Date:** 2026-10-15

## Context

A *data load* is one run of `load_served_unserved`
([0007](0007-loading-and-verifying-the-source-data.md)). A *release* is one
version of an FCC filing period, named by the date its data describes
(`as_of`) and the date the FCC processed it (`processed_on`)
([0006](0006-data-model-for-locations-and-boundaries.md)).

0007 decision 2 makes every data load replace all loaded data: it starts with
one `TRUNCATE` of the ten tables the loader owns. The data-layer review
([#38](https://github.com/ShawnMcCollum/BroadbandMap/issues/38), finding H2)
found three costs:

- `TRUNCATE` takes an `ACCESS EXCLUSIVE` lock on all ten tables, held until
  the load commits, about six minutes for Ohio. That lock mode blocks even a
  plain `SELECT`, so every reader of the loaded data waits for the whole load.
  The API ([#3](https://github.com/ShawnMcCollum/BroadbandMap/issues/3)) would
  be down for six minutes per load.
- The database holds one release at a time, although the schema keeps every
  status and rollup per release.
- Every load gives the release a new id, so nothing outside the database can
  rely on an id.

[#41](https://github.com/ShawnMcCollum/BroadbandMap/issues/41) asks for a load
that adds a release without blocking readers of the others.

[0012](0012-location-placement-per-release.md) stores a location's block and
H3 cell on its status, per release. A release is then its statuses and its
rollups, and only the census boundaries are shared between releases. The June
2025 Ohio file (J25), processed on 1 October 2026, two days after the
December 2025 file (D25), is a ready second release, and one loaded out of
period order.

## Decision

1. **A data load adds one release, beside those already loaded.** In one
   durable transaction it inserts the release, its statuses and its rollups,
   and checks and reconciles them as before (0007 decisions 3 to 7). It
   truncates nothing and never changes another release.
   - Its strongest table locks are `ROW EXCLUSIVE` (`COPY`, `INSERT`,
     `DELETE`) and `SHARE UPDATE EXCLUSIVE` (`ANALYZE`). A `SELECT` takes
     `ACCESS SHARE`, which only `ACCESS EXCLUSIVE` blocks, so no reader waits
     for a load. A test checks that a load holds no `ACCESS EXCLUSIVE` lock.
   - Until it commits, the new release is invisible to everyone else.
2. **The census boundaries are loaded once per state,** by the first data load
   for that state, in the same transaction as its release. A later load finds
   the state's row in `geography_state`, reads the state's block GEOIDs from
   the database and needs no TIGER/Line files. It checks that every block of
   the state has a county subdivision: only a database loaded before
   [0010](0010-place-and-county-subdivision-rollups.md) has one without, and
   it must be emptied and loaded again. A data load never changes boundaries
   that are loaded. The vintage is fixed at 2020
   ([0005](0005-census-tiger-2020-boundaries.md)), so a state's boundaries are
   either all loaded or not at all, and no vintage is stored. A later vintage
   needs its own decision.
3. **One state per database, for now.** A data load for a second state stops
   with an error before it reads any file. FCC files are published per state,
   but a release is named by its two dates only, so a second state raises a
   question this decision does not answer: whether a release is national and
   loaded state by state, or one state's file. The rollups of an H3 cell that
   crosses a state line depend on the answer.
4. **A release is identified by `as_of` and `processed_on`, never by its id.**
   The unique constraint `bdc_release_unique_version` already enforces the
   pair. A load's result names its release by the two dates. The API (#3) and
   the load record (`LoadRun`,
   [#15](https://github.com/ShawnMcCollum/BroadbandMap/issues/15)) address a
   release the same way, and `LoadRun` holds no foreign key to `Release`. Only
   tables the loader owns may hold a foreign key to one of its tables, and a
   test checks it, so deleting a release cannot reach other data.
5. **A release that is already loaded is refused, unless the load is told to
   replace it** (`--replace`). Replacing deletes the release, which cascades
   to its statuses and rollups, and loads it again, in the load's one
   transaction. Readers of that release see the old rows until the load
   commits, and a failed replace leaves the old rows in place. A reprocessed
   file is a new release, because its `processed_on` differs, so no other
   versioning is needed.
6. **Releases can be loaded in any order.** Nothing in a load depends on the
   releases already loaded. Where "latest" matters, it is the latest `as_of`,
   then the latest `processed_on`, the order `Release.Meta.ordering` gives:
   D25 comes before J25 although J25 was processed later.
7. **Reconciliation is per release.** The status and rollup counts were
   already limited to the release. The boundary row counts are compared only
   when the load wrote the boundaries, and are taken for the state, by GEOID
   prefix: every boundary GEOID starts with its state's FIPS code.
8. **The data directory can hold several FCC files.** `--fcc-file` names the
   one to load; a relative path is taken from the data directory. With one
   file, as before, it need not be named.
9. **The statuses are analyzed after every load**, before the rollups are
   built, as before: until then the planner has no statistics for the new
   release. Blocks are analyzed only when the load wrote them. Vacuuming is
   left to [#42](https://github.com/ShawnMcCollum/BroadbandMap/issues/42).

## Measurements

Measured with a prototype of this decision on a copy of the development
database holding D25: PostgreSQL 17.5 with default settings and a 256 MB
`/dev/shm` ([0011](0011-database-shared-memory.md)). These are single runs, so
the timings are indicative; the pull request that implements this decision
repeats them on the development database.

**A second release, and a replace,** with the census boundaries already
loaded:

| Step | J25 added beside D25 | D25 replaced |
|---|---|---|
| Delete the loaded release (4.9 million rows) | — | 3 s |
| Statuses (`COPY`) | 65 s | 62 s |
| Rollups at seven levels | 32 s | 30 s |
| `ANALYZE`, deferred foreign-key checks, reconciliation | 58 s | 59 s |
| **Total** | **155 s** | **154 s** |

A first load into an empty database also loads the boundaries and assigns the
blocks, as under 0007: about 390 s
([#46](https://github.com/ShawnMcCollum/BroadbandMap/issues/46)).

**Readers.** During both loads, a second session read D25 every two to three
seconds, waiting at most one second for a lock: its 88 county rollups, and its
379,790 Franklin County statuses by GEOID prefix. None of the 94 reads waited
for a lock. The rollups took at most 4 ms. The statuses took 283 ms on average
during the J25 load and 456 ms during the replace, against about 90 ms with no
load running: a load competes for CPU and disk, but holds no lock that a
reader waits for. Under 0007, each of these reads waits until the load
commits.

**Storage:**

| | D25 only | D25 and J25 | After replacing D25, before a vacuum |
|---|---|---|---|
| Statuses: heap | 404 MB | 808 MB | 1,211 MB |
| Statuses: indexes | 430 MB | 861 MB | 1,292 MB |
| Rollups: heap and indexes | 110 MB | 147 MB | 207 MB |

Each release adds about 835 MB. A replace leaves about 4.5 million dead status
rows until they are vacuumed.

**Queries on D25 with a second release loaded** (median of three runs,
`EXPLAIN ANALYZE`). The rollup groupings take 6 to 20% longer; selecting an
area's statuses does not:

| | D25 only | D25 and J25 |
|---|---|---|
| County rollup grouping | 762 ms | 912 ms |
| Block rollup grouping | 1,559 ms | 1,659 ms |
| Place rollup grouping | 786 ms | 880 ms |
| Franklin County's statuses by GEOID prefix | 96 ms | 83 ms |

## Alternatives considered

- **Shadow tables swapped by rename.** Each load would fill copies of the ten
  tables and swap them in a short transaction. Readers would wait only for the
  swap, but the swap still takes `ACCESS EXCLUSIVE` locks, every load would
  copy every other release into the new tables, and the renames would fight
  Django's migrations over table, index and constraint names.
- **Keeping replace-all as an option** (`--replace-all`). It would keep a way
  to reload the boundaries, but it is the six-minute outage this decision
  removes, behind a flag. A database that needs new boundaries is emptied and
  loaded again instead.
- **Loading a release that is already loaded replaces it, without asking.**
  Simpler to call, but a scheduled load ([#15](https://github.com/ShawnMcCollum/BroadbandMap/issues/15))
  that picks up a file twice would silently rewrite 4.5 million rows.
- **Versioning a release that is loaded again** (a load number beside the two
  dates). The FCC already versions a period by `processed_on`, so a second
  load of the same file holds the same data.
- **A `state` on `Release`, so that each state's file is its own release.** It
  would allow a second state now, but it decides decision 3's question without
  the API and map that depend on it.
- **Reading the block GEOIDs from the TIGER/Line file on every load.** It
  keeps one code path, but a second release would need the 280 MB block file
  only to learn what the database already holds.

## Consequences

- **Positive:** No reader waits for a data load. A second release loads
  beside the first in under three minutes, while the first stays readable.
- **Positive:** Releases can be compared side by side, and a release keeps
  its id while other releases are loaded.
- **Positive:** Loading a release that is already loaded cannot happen by
  accident.
- **Negative:** A replace deletes 4.5 million status rows. Their space is
  reused only after a vacuum (#42).
- **Negative:** The census boundaries cannot be reloaded by a data load. A
  database whose boundaries must change is emptied and loaded again.
- **Negative:** A second state cannot be loaded yet (decision 3).
- **Negative:** Two data loads can still run at once. Two loads of different
  releases do not conflict, but two loads that both load a state's boundaries,
  or the same release, fail when the first commits.
  [#45](https://github.com/ShawnMcCollum/BroadbandMap/issues/45) makes the
  second one fail at once.
- **Follow-up:** #15 records each load in `LoadRun` by the release's dates,
  with no foreign key to `Release`.
