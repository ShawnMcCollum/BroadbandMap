# 0017 — A release is national, and a data load adds one state

- **Status:** Accepted
- **Date:** 2026-10-16
- **Amends:** [0013](0013-release-scoped-data-loads.md), decisions 3 and 5
- **Related:** [0016](0016-rest-api-contract-and-tests.md), the REST API contract

## Context

[0013](0013-release-scoped-data-loads.md) decision 3 holds one state per
database. It left a question open: is a release national, loaded state by
state, or is it one state's file?

The FCC publishes each release nationally and splits only its download by
state. Its download list names 56 Served/Unserved files per release, one per
state and territory, and all of them carry the same processing date:
13 October 2026 for December 2025, 1 October 2026 for June 2025, and 29 July
2026 for December 2024. The FCC records one "last updated" date per release,
not per state, and offers only the latest processing of each release.

Every census area lies in one state, whose FIPS code starts its GEOID, so the
county, tract, block group, block, place and county subdivision rollups never
cross a state line. H3 cells do. In the December 2025 Ohio data, 1,030 census
blocks touch the state's outline, and their 10,011 locations lie in 1,230 H3
cells. Within 1 km of the outline, 8,733 blocks hold 113,696 locations in 4,261
cells, 3.3% of Ohio's 127,620 cells with locations. A resolution-8 cell is
about 1 km across.

The loader also assumed one state in two places. The geometry check and the
block assignment ran over every state's boundaries.

## Decision

1. **A release is national.** It is one FCC processing of one filing period,
   named by `as_of` and `processed_on` as before (0013 decision 4). Its
   identity and `bdc_release_unique_version` do not change. Each state's file
   is that state's part of the release.
2. **A data load adds one state to a release.** It creates the release if
   none has the file's dates, and otherwise adds the state to the loaded one.
   A state is in a release when the release has a status in one of the
   state's blocks. One lookup in `servedstatus_release_block` answers it, so
   nothing else records it.
3. **"Already loaded" and `--replace` apply to a state in a release.** A load
   of a state the release already holds is refused, unless the load is told
   to replace it. Replacing deletes only that state's statuses and rollups, in
   the load's one transaction, and keeps the release, its id, and every other
   state's rows.
4. **Every rollup row counts one state's statuses** (`Rollup.state`). A census
   area's row is the area's only row in the release, and a constraint checks
   that its code starts with the state's FIPS code. An H3 cell on a state line
   has one row per state, and **a cell's counts in a release are the sum of
   its rows.** No data load writes another state's rows.
5. **Reconciliation is per state in a release.** The statuses counted are those
   in the state's blocks, and the rollups those of the state, at every level
   including H3. Every count is still compared with the file being loaded.
6. **Census boundaries are loaded once per state**, as under 0013 decision 2,
   and a database holds any number of states. The geometry check and the block
   assignment cover only the state being loaded.
7. **A release lists the states it holds,** read from its statuses. One
   release can hold fewer states than another, and "latest" still means the
   latest `as_of`, then `processed_on`. The API
   ([#3](https://github.com/ShawnMcCollum/BroadbandMap/issues/3)) returns a
   release's states with it, so that no client takes a date pair to mean
   national data.
8. **The API and the map name a release by its two dates**
   ([0016](0016-rest-api-contract-and-tests.md) and the
   [REST API guidelines](../api-guidelines.md)). The API adds up an H3 cell's
   rows before returning it, and the map shows the sum.
9. **Deleting a release deletes every state in it.** Removing one state from a
   release is left for later.
10. **A rollup rebuild covers every state of the release,** and removes the rows
    of any state without statuses.

## Measurements

Measured on the development database (PostgreSQL 17.5, D25 and J25 loaded for
Ohio). Single runs, so the timings are indicative.

| | Before | After |
|---|---|---|
| Rollups: heap, after `VACUUM FULL` | 61 MB | 67 MB |
| Rollups: indexes, after `VACUUM FULL` | 52 MB | 59 MB |
| Migration (757,792 rollup rows) | — | 20 s |
| Replacing J25 | 154 s (0013) | 177 s and 168 s |
| Block assignment, Ohio | 27 s (0010) | 23 s |

Most of the difference in the J25 replace is run-to-run variation. Its
statuses' `COPY`, which this decision does not change, took 78 s and 64 s
against 62 s in 0013; its rollups took 32 s and 35 s against 30 s. The first
run followed the 12-minute full-data suite.

Adding the state's filter to the rollup groupings keeps their plan, a parallel
sequential scan over the release's statuses, within single-run noise. Asking
whether a release holds a state is an index scan of 0.07 ms.

## Alternatives considered

- **One release per state's file**, with a state on `Release` and in its unique
  constraint. The FCC numbers a processing nationally, so the same two dates
  would name several releases. The API would have to group them back to answer
  any question about more than one state, and "latest" would differ by state.
- **One national row per H3 cell,** rebuilt for the cells a load touches.
  Loading or replacing one state would then rewrite rows that count another
  state's locations, and the H3 rollups could no longer be reconciled against
  the file being loaded.
- **A release named by its filing period alone,** each state keeping its own
  processing date. One release would then mix FCC processings, and a
  reprocessed state would replace the earlier data under the same name, which
  0013 decision 5 avoids.
- **A table recording each state loaded into a release.** The statuses already
  say which states a release holds, through an index, and a second record of
  the same fact could disagree with them. `LoadRun`
  ([#15](https://github.com/ShawnMcCollum/BroadbandMap/issues/15)) will record
  each load.
- **A state column on the statuses.** A status's state is the first two digits
  of its block's GEOID, and the index on (`release`, `block`) serves that
  prefix.

## Consequences

- **Positive:** A second state loads beside the first without changing any of
  its rows, and every state of a release can be read together.
- **Positive:** A release keeps its id when one of its states is replaced.
- **Positive:** A release is named as before, so the API's public identifiers
  do not change.
- **Negative:** Every H3 read must add up a cell's rows. Census-level reads are
  unchanged.
- **Negative:** The FCC offers only the latest processing of each release, so
  two states downloaded at different times can belong to different releases.
  Downloading them from the same processing puts them in one release.
- **Negative:** Undoing the migration fails once a release holds two states'
  rows for one H3 cell.
- **Follow-up:** removing one state from a release; #3 adds up H3 rows and
  returns each release's states; #15 records the state of each load.
