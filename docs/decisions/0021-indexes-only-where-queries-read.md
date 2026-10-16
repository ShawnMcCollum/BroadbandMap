# 0021 — An index only where a query reads through it

- **Status:** Accepted
- **Date:** 2026-10-16
- **Amends:** [0012](0012-location-placement-per-release.md), decision 2
- **Amended by:** [0022](0022-status-admin-pages-read-an-index.md), which adds `servedstatus_not_served`
- **Related:** [0008](0008-served-not-served-rollups.md), [0017](0017-national-releases-loaded-by-state.md), [0019](0019-location-cursors.md), [#43](https://github.com/ShawnMcCollum/BroadbandMap/issues/43)

## Context

Django adds indexes that no decision chose. It indexes every field with
`db_index=True` and every foreign key that does not set `db_index=False`. On
PostgreSQL it adds a second, `varchar_pattern_ops` index beside each of those
on a `varchar` column, for `LIKE`.
[0012](0012-location-placement-per-release.md) kept the `location_id` index on
the statuses for the admin's search by location ID, and left the decision to
[#43](https://github.com/ShawnMcCollum/BroadbandMap/issues/43).

Every data load maintains each index row by row. Since
[0017](0017-national-releases-loaded-by-state.md), a release is national, so
the statuses grow by about 4.5 million rows for each Ohio-sized state in each
release, and the census blocks by each new state's blocks, 276,428 for Ohio.

Each index on the loaded tables was compared with the queries that read those
tables: the area keys (`statuses_in`), the loader, reconciliation, the rollup
builds, the API, the admin and the full-data suite. The plans were taken with
`EXPLAIN ANALYZE`, before and after dropping the candidates inside a
transaction that was rolled back. Sixteen indexes are read by no query, or only
where a plain index on the same column serves the same query:

| Index | Size, two releases | Read by |
|---|---|---|
| `served_unserved_servedstatus_location_id_bc098ed3` (`location_id`) | 194.3 MB | the admin's search by location ID; the location drill-down's deep pages of large census areas, beside `servedstatus_release_block` |
| `geography_block_block_group_id_acdab8a4` and its `_like` | 5.1 MB + 5.1 MB | nothing |
| `geography_block_place_id_a11eda9a_like` | 5.2 MB | `statuses_in` at the place level, which the plain index serves as well |
| `geography_block_county_subdivision_id_39bb3bbc_like` | 5.5 MB | `IS NULL` checks and `statuses_in`, which the plain index serves as well |
| The plain and `_like` indexes on `BlockGroup.tract`, `Tract.county`, `County.state`, `Place.state` and `CountySubdivision.county`, and the `_like` index on `State.abbreviation` | 0.6 MB in all | nothing; `county_geometries` filters counties by state with a sequential scan of 88 rows |

The FCC file lists its locations in ascending `location_id`, so each state's
statuses reach the unique `(release, location_id)` index in key order.

## Decision

1. **No index leads with `ServedStatus.location_id`.** The field loses
   `db_index=True`. A search for one location names every release,
   `release_id IN (…)`, and the unique index
   `served_unserved_unique_location_per_release` on `(release, location_id)`
   finds it with one descent per release. The API's `require_area` already
   probes H3 cells release by release in the same way. The admin's search by
   location ID does this for its page and its count. Without the release list,
   the count is a sequential scan of every status: 347 ms for two Ohio
   releases.
   - The location drill-down ([0019](0019-location-cursors.md)) used the
     index on deep pages of large census areas. There the planner combined its
     range, `location_id > <cursor>`, with the area's
     `servedstatus_release_block` bitmap. Those pages now read the unique
     index's range within the release, without the area's bitmap: the
     all-statuses page by a bitmap scan of it, the not-served page by an index
     scan. The unique index offers the same range for one release, and the
     dropped index's range grew with every release.
2. **The unique constraint keeps its order, `(release, location_id)`.**
   Leading it with the location would let it replace the dropped index, but
   every release after the first would then be inserted throughout it, and the
   migration would rebuild the largest status index.
3. **Boundary foreign keys have no automatic index.** All eight are
   `db_index=False`: `County.state`, `Tract.county`, `BlockGroup.tract`,
   `Block.block_group`, `Block.place`, `Block.county_subdivision`,
   `Place.state` and `CountySubdivision.county`. None has a
   `varchar_pattern_ops` index, since nothing compares a foreign key with
   `LIKE`.
4. **Two plain indexes on blocks are declared explicitly:** `block_place` on
   `place` and `block_county_subdivision` on `county_subdivision`.
   `statuses_in` selects a place's or county subdivision's blocks through them.
   The loader, `build_rollups` and the full-data suite look for blocks without
   a county subdivision.
5. **A boundary's link to its parent area has no index, `Block.block_group`
   included.** A boundary's parent is named by the first digits of its own
   GEOID, which the full-data suite checks for every row. A read of an area's
   children is therefore a GEOID prefix read, served by the GEOID index, and no
   code reads through the link. `County.state` is read by the county GeoJSON,
   but the planner scans the table either way: 88 rows for Ohio, about
   3,200 nationally.
6. **`State.abbreviation` is unique through a named constraint,**
   `geography_state_unique_abbreviation`, instead of `unique=True`, whose
   `varchar_pattern_ops` index nothing read.
7. **These indexes stay, each read by a named query:**
   - Each boundary's primary key, and its GEOID `varchar_pattern_ops` index.
     The latter serves the state-prefix reads of the loader, reconciliation
     and the geometry check. With one state loaded, the planner reads the
     primary key for them instead, because every row matches. With several
     states, the prefix is selective. Foreign-key checks and `require_area`
     look GEOIDs up through either index.
   - The statuses' primary key, the unique `(release, location_id)` index,
     `servedstatus_release_block` and `servedstatus_release_h3`
     ([0012](0012-location-placement-per-release.md)).
     - *Amended by [0022](0022-status-admin-pages-read-an-index.md):*
       `servedstatus_not_served` stays as well, a partial index on
       `(release, location_id)` where `NOT any_100_20`, read by the admin's
       not-served filter and the location drill-down's not-served pages.
   - The rollups' primary key, their unique index and
     `rollup_release_state_level`
     ([0017](0017-national-releases-loaded-by-state.md)).
   - `bdc_release`'s primary key and `bdc_release_unique_version`.
8. **A test lists the B-tree indexes of every loaded table**
   (`test_loader_tables_have_only_the_indexes_queries_use`). An index that a
   field adds by default, such as a new foreign key's, fails it until a
   decision names the query that reads it.

The GiST indexes on boundary geometries and internal points are not part of
this decision.

## Measurements

Measured on freshly created development databases, PostgreSQL 17.5 with
default settings and a 256 MB `/dev/shm`
([0011](0011-database-shared-memory.md)). Each was loaded with Ohio's December
2025 and then its June 2025 release, once with the previous indexes and once
with these. These are single runs, so the timings are indicative.

**Index sizes after both loads, MB:**

| Table | Before | After |
|---|---|---|
| `served_unserved_servedstatus` | 861.2 | 666.9 |
| of which the `location_id` index | 194.3 | — |
| `geography_block` | 109.3 | 88.6 |
| Other boundary tables | 3.6 | 2.7 |
| `served_unserved_rollup` | 90.1 | 90.2 |
| **All loaded tables** | 1064.2 | 848.4 |

**Data load steps, seconds:**

| Step | December 2025, before | December 2025, after | June 2025, before | June 2025, after |
|---|---|---|---|---|
| Census boundaries | 219 | 158 | — | — |
| Block assignment | 138 | 92 | — | — |
| Statuses `COPY` | 65 | 54 | 69 | 49 |
| Rollups | 34 | 31 | 36 | 32 |
| Foreign-key check | 74 | 60 | 60 | 52 |
| Reconciliation | 2 | 2 | 3 | 2 |
| Other | 11 | 8 | 1 | 1 |
| **Load total** | 543 | 405 | 169 | 136 |
| Vacuum and analyze | 3 | 3 | 2 | 2 |

Steps this decision does not change, the rollups and the foreign-key check,
were also 10–20% faster in the second database, so part of each difference is
run-to-run variance. The steps that write through a dropped index changed
most: the June 2025 statuses `COPY`, whose rows the `location_id` index took in
the middle of its pages, and the census blocks' `COPY` and block assignment,
which maintained the four dropped block indexes.

Migrating the loaded database in place took 1.7 s for the boundary tables,
including re-checking the foreign keys whose constraints Django re-adds, and
0.06 s for the statuses.

**Location drill-down, county 39035, median of seven runs, ms:**

| Query | Before | After |
|---|---|---|
| First page, all statuses | 82.6 | 82.0 |
| Page after the 90% position, all statuses | 42.5 | 40.2 |
| Page after the 90% position, not served | 13.6 | 6.2 |

**Query plans.** Every query path above uses the same plan as before, or the
same with `block_place` or `block_county_subdivision` in place of a dropped
index. The exceptions are the county's deep drill-down pages, in the table
above. The admin's search by location ID uses the unique index, with
`Index Cond: ((release_id = ANY (…)) AND (location_id = …))`, in 0.053 ms for
its page and 0.025 ms for its count.

## Alternatives considered

- **Keep the `location_id` index.** It costs 194.3 MB for two releases, and a
  further index maintained by every load. In return it serves one admin search
  that the unique index also serves. It saved no time on the deep drill-down
  pages of the largest county in these measurements: they took 42.5 ms (all
  statuses) and 13.6 ms (not served) with it, and 40.2 ms and 6.2 ms without.
- **Lead the unique constraint with the location** and drop the `location_id`
  index. See decision 2.
- **A composite primary key on `(release, location_id)`,** removing the `id`
  column and its index. Django 5.2's admin does not register a model with a
  composite primary key, so the status admin would go.
- **Drop the GEOID `varchar_pattern_ops` indexes.** The primary key's default
  operator class cannot serve `LIKE 'xx%'` in the database's `en_US.utf8`
  collation ([0008](0008-served-not-served-rollups.md)), and with several
  states loaded the prefix reads need an index.
- **Keep a plain index on every boundary foreign key.** No query reads
  through six of the eight.

## Consequences

- **Positive:** Two Ohio releases take 215.8 MB less in indexes, 194.3 MB of
  it the `location_id` index, about 97 MB per release. Loads are faster: the
  June 2025 statuses `COPY` took 49 s instead of 69 s, and the census blocks'
  `COPY` and block assignment 238 s instead of 338 s, part of it run-to-run
  variance.
- **Positive:** The inventory test turns this decision into a check.
- **Negative:** A search for one location makes one index descent per
  release, so its cost grows with the number of releases.
- **Negative:** A deep drill-down page of a large census area can no longer
  combine the dropped index's range with the area's bitmap. No page was slower
  on these databases: for the largest Ohio county, the page after the 90%
  position took 40.2 ms instead of 42.5 ms (all statuses) and 6.2 ms instead
  of 13.6 ms (not served). A profile of a development database that had been
  through repeated loads measured the all-statuses page about 14 ms slower, so
  the cost depends on the plan the planner chooses.
- **Negative:** Deleting a parent boundary row would scan its child table
  once per deleted row. Boundaries are loaded once per state and never
  deleted; the tests empty them with `TRUNCATE`.
- **Negative:** A new foreign key on a loaded table must set `db_index=False`
  or name the query its index serves.
