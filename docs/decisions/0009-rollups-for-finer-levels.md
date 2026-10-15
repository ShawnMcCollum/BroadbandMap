# 0009 — Rollups by tract, block group, block and H3 cell

- **Status:** Accepted
- **Date:** 2026-10-15
- **Amended by:** [0010](0010-place-and-county-subdivision-rollups.md), which adds the place and county subdivision levels, and [0012](0012-location-placement-per-release.md), which groups and selects through the block and H3 cell stored on each status

## Context

The terms are those of [0008](0008-served-not-served-rollups.md). A *rollup* is
one row of Served/Not served counts for one area in one release. An *area key*
is the pair (level, code) that names an area, for example (`county`, `39049`)
for Franklin County. The same key selects the locations behind the row.

0008 built the county rollups and recorded the area key of every level.
[#28](https://github.com/ShawnMcCollum/BroadbandMap/issues/28) builds the
tract, block group, block and H3 resolution-8 levels, so that the API
([#3](https://github.com/ShawnMcCollum/BroadbandMap/issues/3)) and the
drill-down
([#26](https://github.com/ShawnMcCollum/BroadbandMap/issues/26)) can serve them.

H3 is the first level whose code is not a GEOID prefix, so the rule in 0008
that a level is a choice and a GEOID length no longer fits.

The areas that have locations, in the December 2025 Ohio data:

| Level | Areas | Most locations in one area | Fewest |
|---|---|---|---|
| county | 88 | 430,799 | 6,670 |
| tract | 3,162 | 5,211 | 4 |
| block group | 9,459 | 2,843 | 1 |
| block | 235,550 | 807 | 1 |
| H3 resolution-8 cell | 127,620 | 1,282 | 1 |

That is 375,879 rollup rows per release, 375,791 of them new. H3 cells do not
nest inside census areas: 3,617 cells hold locations from more than one county.

## Decision

1. **Four levels join county: tract, block group, block and H3 resolution-8
   cell.** Every data load and the `build_rollups` command build all five.
   Places and county subdivisions follow in
   [#30](https://github.com/ShawnMcCollum/BroadbandMap/issues/30). They need a
   block-to-area assignment first (0008).
2. **Each level is defined by an area key, in one table, `AREA_KEYS`.** An
   entry gives:
   - the form of a code, as a regular expression and in words for error
     messages
   - the expression that gives the code of a status's area, used to group
   - the lookup that selects an area's statuses by its code

   The check constraint, `build_rollups` and `statuses_in` all read the table,
   so a level is added in one place. It replaces `GEOID_LENGTHS`, which only
   fits GEOID prefixes. The levels #30 adds fit it too, with a code read from a
   stored block-to-area column.
3. **The area keys are these.**

   | Level (value) | Code | Grouped by | A location is in the area when |
   |---|---|---|---|
   | `county` | 5 digits | `Left(block GEOID, 5)` | its block GEOID starts with the code |
   | `tract` | 11 digits | `Left(block GEOID, 11)` | its block GEOID starts with the code |
   | `block_group` | 12 digits | `Left(block GEOID, 12)` | its block GEOID starts with the code |
   | `block` | 15 digits | the block GEOID | its block GEOID is the code |
   | `h3_res8` | 15 lowercase hex characters | the cell index | its `h3_res8` is the code |

   - Levels whose code is a prefix keep `startswith`. Levels whose code is the
     whole value use `=`. It is as fast, uses the plain btree index, and gives
     row estimates closer to the truth (53 rows rather than 452 for a block),
     which the paged queries of #26 will rely on.
   - The H3 code's form is exactly the `bdc_location_h3_res8_format`
     constraint, so every loaded cell has a valid code.
   - The value `h3_res8` names the resolution, so another resolution can be
     added later as a level of its own.
   - The labels are `County`, `Census tract`, `Block group`, `Census block` and
     `H3 resolution-8 cell`, following the boundary models' verbose names and
     the `h3_res8` help text on `Location`.
4. **The loader analyzes `bdc_location` and `served_unserved_servedstatus` once
   both are written, before it builds the rollups.** This takes 0.5 s and cuts
   the grouping inside a load from about 77 s to about 14 s. After the load's
   `TRUNCATE`, PostgreSQL treats both tables as empty until they are analyzed,
   and plans the grouping badly. The reconciliation queries read the same
   tables, so they may gain too.
5. **`build_rollups(release, level)` builds one level,** in its own
   `transaction.atomic()` (a savepoint inside a load).
   - The loader builds the levels in order and reports each one, for example
     `rollups by tract: 3,162 rows in 2 s`. This is how each level's cost in a
     load is measured, and later loads keep reporting it.
   - The `build_rollups` command rebuilds every level of a release in one
     transaction, so a failure keeps that release's previous rollups. It takes
     about 40 s.
6. **Rows are still written with `bulk_create`.** `INSERT … SELECT` would save
   about 11 s per build. It needs raw SQL built around the ORM's compiled
   query, which depends on that query's column order. It is recorded as an
   alternative below.
7. **Every data load checks that each level adds up to the state's totals.**
   - `Counts` gains a `rollup_totals` section with keys like
     `"tract:wired_100_20"`.
   - The source side is the state's totals for each count, summed from the
     county counts the load already tallies from the CSV. Every location lies in
     exactly one area at each level, so every level must add up to the same
     totals. This costs nothing per row.
   - The database side is one `GROUP BY level` over the release's rollups.
   - This catches a level that drops or double-counts locations. County rows
     are still reconciled one by one, as in 0008.
8. **The full-data suite compares every area at every level with the
   independent CSV reader.** The reader works out each row's codes from the CSV
   columns itself, without the application's area keys.
9. **The full-data suite checks the selection rule** for every county, tract
   and block group, and for every 100th block and H3 cell in code order.
   Checking every block and cell would add about 11 minutes. Every 100th adds a
   few seconds, and within a level the rule is the same for every area.
10. **The admin's search help text names H3 cells.** The search stays an exact
    match on the code.

## Measurements

Measured on the December 2025 Ohio data, in a development database running
PostgreSQL 17.5 with default settings (`shared_buffers` 128 MB, `work_mem` 4 MB,
two parallel workers).

**Building rollups on data already loaded,** with current planner statistics:

| Level | `GROUP BY` | `bulk_create` (batches of 1,000) |
|---|---|---|
| county | 2.0 s | — |
| tract | 2.1 s | 0.2 s |
| block group | 2.1 s | 0.5 s |
| block | 4.3 s | 12.8 s |
| H3 cell | 2.6 s | 7.3 s |

- `INSERT … SELECT` of the same `GROUP BY` took 8.7 s for blocks and 7.5 s for
  H3 cells, grouping included. With `bulk_create` the same work takes 17.1 s
  and 9.9 s.
- `connection.check_constraints()` with 363,170 new block and H3 rows pending
  took 2.2 s.

**Building rollups inside a data load.** Each level was grouped and inserted in
turn in a real load of the real files, rolled back at the end. It was then
grouped a second time, and a third time after `ANALYZE`:

| Level | `GROUP BY` | Again | After `ANALYZE` | Insert |
|---|---|---|---|---|
| county | 11.0 s | 10.3 s | 2.0 s | 0.0 s |
| tract | 13.4 s | 12.9 s | 2.0 s | 0.2 s |
| block group | 15.6 s | 14.9 s | 2.7 s | 0.7 s |
| block | 21.7 s | 18.0 s | 4.6 s | 13.2 s |
| H3 cell | 15.5 s | 15.0 s | 2.7 s | 7.1 s |

- The slowness is not a first-read cost, because the second pass is as slow as
  the first.
- After the load's `TRUNCATE`, `pg_class` shows `reltuples` −1 and `relpages` 0
  for `served_unserved_servedstatus` and `bdc_location`. The planner treats
  both as empty. It estimates one row and plans a nested loop of 4.5M index
  lookups, followed by an external merge sort that spills 126 MB to disk.
  `EXPLAIN ANALYZE` of the county query took 11.1 s.
- `ANALYZE` of both tables inside the load's transaction took 0.5 s and
  restored the 2 s plans.
- This is the cause of the 10 s county build that 0008 measured inside a load.
  0008 put it down to a first read with no planner statistics. The statistics
  are the cause, not the first read.
- The load's foreign-key check took 85 s with all rollups pending. On loaded
  data, 363,170 new rollup rows took 2.2 s to check, so nearly all of the 85 s
  is the existing check of locations and statuses.
- With `ANALYZE`, profiling put the five levels at about 38 s inside a load:
  0.5 s to analyze, 14 s to group, 21 s to insert and about 2 s more in the
  foreign-key check. The county build cost 10 s before, so a load was expected
  to take about 28 s longer. Without `ANALYZE` the five levels would cost about
  100 s.

**The real load with this change,** from the `rollups by …` lines it prints:

| Step | Time |
|---|---|
| County rollups | 2 s |
| Tract rollups | 2 s |
| Block group rollups | 3 s |
| Block rollups | 20 s |
| H3 cell rollups | 11 s |
| **All five levels** | **38 s** |
| **Whole load** | **432 s** |

The load does not time the `ANALYZE` step, which took 0.5 s when profiled. The
rollup steps took 38 s, against 10 s for the county rollups alone in 0008. The
whole load took 432 s, against 387 s for the load measured in
[#22](https://github.com/ShawnMcCollum/BroadbandMap/issues/22). Part of
that 45 s difference is variation between runs: writing the census blocks took
165 s in this load and 182 s in the profiling load.

The `served_unserved_rollup` table takes 68 MB with its indexes, 30 MB without.
The full-data suite, which does two full loads and compares all five levels,
takes about 18 minutes.

**Selecting one area's statuses,** timed over 500 random areas per level with
the aggregate the full-data suite uses:

| Level | Lookup | Per area | Every area |
|---|---|---|---|
| tract | `location__block__geoid__startswith` | 11.6 ms | 37 s |
| block group | `location__block__geoid__startswith` | 5.2 ms | 49 s |
| block | `startswith` / exact | 2.0 / 1.8 ms | 480 / 425 s |
| H3 cell | `location__h3_res8__startswith` / exact | 1.9 / 1.8 ms | 239 / 234 s |

- For a block or an H3 cell, both lookups give an index scan on `bdc_location`
  and a nested loop into the statuses.
- The planner estimates 452 rows for one block with `LIKE` and 53 with `=`. A
  block averages 19 locations. For one H3 cell it estimates 440 with `LIKE` and
  170 with `=`.

**Tallying the CSV,** read from the zip in the backend container:

| Read of the FCC CSV | Time |
|---|---|
| `read_locations` with the loader's tally | 41 s |
| The same, also tallying four counts for every area of the four new levels | 83 s, with 1,503,164 counter keys |
| The independent reader's `csv.DictReader` alone | 12 s |
| The independent reader, also counting every area at all five levels | 29 s, with 375,879 areas; the process peaked at 331 MB |

The independent reader runs once per full-data suite, so counting every area
there costs 17 s.

## Alternatives considered

- **Extending `GEOID_LENGTHS` with a special case for H3.** The code form,
  grouping and selection would each need their own branch.
- **One prefix rule (`startswith`) for every level.** It is as fast, but its
  row estimates are 8 times too high for a block.
- **`INSERT … SELECT` instead of `bulk_create`.** It is about 11 s faster per
  build, at the price of raw SQL tied to the ORM query's column order.
- **Tallying every area of every level from the CSV in each load.** It adds
  42 s to every load and holds 1,503,164 counter keys in memory.
- **Checking that each census area adds up to its parent.** Tracts to counties,
  and so on down the census levels. H3 cells cross county lines, so it could
  not cover H3, and the totals check covers every level.
- **Building without `ANALYZE`.** It costs about 65 s more per load.
- **Not storing block and H3 rollups, and aggregating on request.** A map of H3
  cells needs all 127,620 at once, which takes 2.6 s per view.
- **Checking the selection rule for every block and H3 cell in the full-data
  suite.** It adds about 11 minutes.

## Consequences

- **Positive:** #3 and #26 can serve all five levels, and a map by H3 cell is
  an index read.
- **Positive:** A level is one entry in `AREA_KEYS`, which #30 builds on.
- **Positive:** The `ANALYZE` also speeds up the county build and the queries
  that follow it in the load.
- **Negative:** The table holds 375,879 rollup rows per release, and takes
  68 MB with its indexes.
- **Negative:** Building the rollups takes 38 s of each data load, against
  10 s for the county rollups alone.
- **Negative:** Each load checks the finer levels only by their totals. Their
  per-area counts are checked by the full-data suite.
- **Supersedes:** Decision 5 of 0008 (county is the only level built), and the
  rule in its decision 3 and Consequences that a level is one choice and one
  GEOID length.
