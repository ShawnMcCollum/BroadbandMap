# 0010 — Rollups by place and county subdivision

- **Status:** Accepted
- **Date:** 2026-10-15
- **Follow-up:** [0011](0011-database-shared-memory.md) raises the database container's `/dev/shm` to 256 MB

## Context

The terms are those of [0008](0008-served-not-served-rollups.md) and
[0009](0009-rollups-for-finer-levels.md). A *rollup* is one row of Served/Not
served counts for one area in one release. An *area key* is the pair (level,
code) that names an area, for example (`place`, `3918000`) for Columbus city.
The same key selects the locations behind the row. A block's *internal point* is
the Census point inside it (`INTPTLAT20`/`INTPTLON20`), stored as
`Block.internal_point`.

0008 recorded that places and county subdivisions need a block-to-area
assignment first, because their GEOIDs are not prefixes of a block's GEOID.
[#30](https://github.com/ShawnMcCollum/BroadbandMap/issues/30) builds the
assignment and the two levels, so that the API
([#3](https://github.com/ShawnMcCollum/BroadbandMap/issues/3)) and the
drill-down
([#26](https://github.com/ShawnMcCollum/BroadbandMap/issues/26)) can serve them
with the same area keys as every other level.

**How the 276,428 Ohio blocks fall within places and county subdivisions,**
from the 2020 TIGER/Line files in the development database:

| | Places (1,265) | County subdivisions (1,606) |
|---|---|---|
| Blocks whose internal point lies in exactly one area | 155,805 | 276,428 |
| … in no area | 120,623 | 0 |
| … in two or more areas | 0 | 0 |
| Blocks wholly inside one area (`ST_Covers`) | 130,640 | 225,916 |
| Blocks partly outside the area holding their point | 25,165, each with at least 99.988% of its area inside | 50,512, each with at least 99.983% inside (at most 82 m² outside) |
| Largest share of a block inside an area that does not hold its point | 0.000031% (0.0017 m²) | 0.000076% |
| Blocks straddling a boundary (more than 0.1% of their area on each side) | 0 | 0 |

- The partial overlaps are slivers along shared boundaries. Every block lies
  within one place or none, and within exactly one county subdivision.
- In every case, the area holding a block's internal point is the area that
  covers most of the block. The two rules give the same assignment for every
  Ohio block.
- Every block's county subdivision is in the block's own county, as county
  subdivisions nest within counties.

**The areas that have locations,** in the December 2025 Ohio data:

| Level | Areas with locations | Most locations in one area | Fewest |
|---|---|---|---|
| place | 1,265 of 1,265 | 235,546 (Columbus city, `3918000`) | 29 |
| county subdivision | 1,597 of 1,606 | 230,564 (Columbus city, `3904918000`) | 2 |

- 3,024,507 locations lie in a place and 1,517,843 (33%) in none.
- That is 2,862 new rollup rows per release, 378,741 in all.
- 82 places hold blocks in more than one county. 76 of them hold locations in
  more than one county. Columbus city (`3918000`) spans three counties.
- Five county subdivisions are named "County subdivisions not defined"
  (`3900700000`, `3903500000`, `3904300000`, `3908500000`, `3909300000`). They
  are the Lake Erie water areas, with no land. Lake blocks are assigned to them,
  and they hold no locations.
- The nine county subdivisions without locations are those five, Wayne township
  (Montgomery County), and the Greene, Hamilton and Morrow County parts of
  Dayton, Fairfield and Galion cities.

## Decision

1. **A block stores its place and county subdivision, as two foreign keys on
   `Block`.**
   - `Block.place` and `Block.county_subdivision`, `on_delete=PROTECT`,
     `related_name="blocks"`.
   - Both are nullable in the schema. A block outside every place has no place.
     `county_subdivision` is nullable only because the loader writes blocks with
     `COPY` before it can assign them, and PostgreSQL cannot defer `NOT NULL`.
     Every load checks that no block lacks one (decision 4).
   - With the columns on `Block`, a rollup groups by a stored value and
     `statuses_in` selects by it, one join from a location to its block. A
     separate assignment table would add a join to every place and
     county-subdivision query (see Alternatives considered).
2. **A block is in the place and the county subdivision that hold its internal
   point** (`ST_Intersects(area.geom, block.internal_point)`).
   - Blocks nest within both, so the area holding a point inside the block is
     the block's area. For every Ohio block, this matches the area that covers
     most of the block.
   - A county subdivision is matched only in the block's own county. County
     subdivisions nest within counties.
   - `ST_Intersects`, not `ST_Contains`. A point on a boundary shared by two
     areas then matches both and is reported (decision 4), rather than matching
     neither.
3. **The loader assigns every block with one SQL `UPDATE`, straight after the
   boundary geometries are checked.**
   - The `UPDATE` reads the two joins as `MATERIALIZED` CTEs, so each area's
     polygon is prepared once. It sets every block, including blocks no area
     holds, so a block keeps no earlier area.
   - The SQL is written by hand in a new module, `etl/assign.py`. The ORM
     cannot join two unrelated tables on a spatial test. It writes a subquery
     per block, which took 63 s.
   - It takes about 27 s per load, with no `ANALYZE` first.
4. **Every data load checks the assignment, and stops with a `LoadError` if:**
   - a block's internal point lies in two places, or in two county subdivisions
     of its county. This is checked before the `UPDATE`, which would otherwise
     keep one of the two silently (4.5 s).
   - a block has no county subdivision after the `UPDATE` (1.3 s).

   A check constraint, `geography_block_county_subdivision_in_county`, also
   requires a block's county subdivision GEOID to start with the block's county
   GEOID. The join already makes this so; the constraint keeps the rule in the
   schema.
5. **Two levels join the rollups: `place` and `county_subdivision`.**
   - `RollupLevel` gains `PLACE = "place", "Place"` and
     `COUNTY_SUBDIVISION = "county_subdivision", "County subdivision"`, after
     `H3_RES8`. The values match the loader's level labels, and the labels the
     models' verbose names. The loader builds and reports them after the other
     five.
   - Their `AREA_KEYS` entries:

     | Level (value) | Code | Grouped by | A location is in the area when |
     |---|---|---|---|
     | `place` | 7 digits | `F("location__block__place")` | its block's place is the code |
     | `county_subdivision` | 10 digits | `F("location__block__county_subdivision")` | its block's county subdivision is the code |

   - `AreaKey` gains a field, `covers_every_location`. It is `False` for
     `place`, because a location outside every place has no place, and `True`
     for every other level.
   - `build_rollups` leaves out statuses with no area at the level, so a
     location outside every place adds to no place row. The filter is applied
     at every level, where it removes nothing.
   - `statuses_in` does not change. It selects by the stored column, so #26 can
     page through an area's locations by index.
6. **The loader analyzes `geography_block` together with the locations and
   statuses, before the rollups.** This adds about 0.8 s. After the load's
   `TRUNCATE`, the planner treats the block table as empty until it is analyzed,
   as 0009 found for locations and statuses. The progress line becomes
   `Analyzing blocks, locations and statuses`.
7. **Every level, place included, must still add up to the state's totals in
   each load.**
   - The source side does not change: `expected_rollup_totals` covers every
     level in `RollupLevel`.
   - On the database side, a level whose key does not cover every location also
     counts the release's statuses outside every one of its areas (1.4 s for
     places). This checks that the place rollups neither drop nor double-count a
     location.
   - It does not check the assignment itself, which decisions 4 and 9 cover.
8. **`build_rollups` refuses to run while any block has no county
   subdivision.** A database migrated but not reloaded has unassigned blocks.
   Without this check, the command would rebuild every other level and silently
   leave no place or county-subdivision rows. The error tells the user to run
   `load_served_unserved`. A command that only assigns blocks is not added.
9. **The full-data suite checks the assignment and the new levels:**
   - every block has a county subdivision
   - every block lies within its own place and county subdivision, and outside
     every other, to 0.1% of its area. This is the largest-overlap rule,
     computed independently of the internal point (about 98 s).
   - the place and county-subdivision rollups equal the independent CSV
     reader's block counts, added up by each block's stored area. The CSV has no
     place column, so the reader's block counts are the independent side.
   - the selection rule, for every place and every county subdivision (about
     60 s)
10. **The admin's block list shows each block's place and county subdivision
    IDs.** The change view already shows both, as read-only links.

The area keys, with the two new levels:

| Level | Code | A location is in the area when |
|---|---|---|
| county | 5-digit GEOID | its block GEOID starts with the code |
| tract | 11-digit GEOID | its block GEOID starts with the code |
| block group | 12-digit GEOID | its block GEOID starts with the code |
| block | 15-digit GEOID | its block GEOID equals the code |
| H3 resolution 8 | 15-character cell index | its `h3_res8` equals the code |
| place | 7-digit GEOID | its block's stored place equals the code |
| county subdivision | 10-digit GEOID | its block's stored county subdivision equals the code |

## Measurements

Measured on the December 2025 Ohio data and the 2020 TIGER/Line files, in a
development database running PostgreSQL 17.5 and PostGIS 3.5.2 with default
settings (`shared_buffers` 128 MB, `work_mem` 4 MB, two parallel workers). Every
measurement that wrote to the database ran in a transaction that was rolled
back.

**Ways to assign blocks,** timed on the loaded data:

| Approach | Time |
|---|---|
| Join of places to blocks by internal point (places outer, GiST index on `internal_point`) | 1.2 s |
| The same for county subdivisions, restricted to the block's county | 1.3 s |
| Assigning by largest overlap instead (intersection areas of every touching pair) | 38 s for places, 60 s for county subdivisions |
| `UPDATE geography_block` with one correlated subquery per block, as the ORM writes it | 62.6 s |
| `UPDATE geography_block` from the two joins, as `MATERIALIZED` CTEs | 27.2 s |
| The same without `MATERIALIZED` | 31.0 s; the planner probes the places once per block, about 9 s instead of 1 s |
| `INSERT` into a separate narrow table from the two joins | 7.1 s |

- A correlated subquery is slow because each block meets a different polygon,
  so PostGIS cannot reuse a prepared geometry. With the area tables outer, each
  area's polygon is prepared once and tested against all the points inside its
  bounding box.
- The `UPDATE` costs 27 s because it rewrites all 276,428 block rows and every
  index on the table (two GiST, seven B-tree). The joins themselves take 2.5 s.
- `UPDATE … FROM` keeps one arbitrary match when a block has two (PostgreSQL
  documents this). A block with two areas has to be found by a separate query.

**Inside a data load.** The boundary files were loaded as the loader does it,
then the assignment ran:

| Step | Time |
|---|---|
| `UPDATE` from the materialized joins, straight after the `COPY` (no planner statistics) | 27.4 s |
| The same plan after `ANALYZE` of the three tables (0.9 s) | identical plan |
| Foreign-key check of everything pending, including the new columns | 3.0 s |

- `MATERIALIZED` fixes the plan's shape, so the assignment does not depend on
  statistics, and needs no `ANALYZE` first.
- The rollups read `geography_block.place_id` and `county_subdivision_id`. After
  the load's `TRUNCATE`, the planner treats the block table as empty until it is
  analyzed, as 0009 found for locations and statuses. So the block table is
  analyzed with them before the rollups are built (0.8 s).

**A separate assignment table was tried and dropped.** It is faster to fill
(7.1 s), but every place and county-subdivision query then joins one more table.
Grouping statuses by county subdivision through it failed, twice and
repeatably, with `could not resize shared memory segment … No space left on
device`. The `postgis` container has Docker's default 64 MB `/dev/shm`, and the
extra parallel hash join outgrew it. With the columns on `geography_block`, the
same grouping runs in 2.7 s.

**Checks, rollups and selection,** timed with the code of this change (assignment
columns in place, block table analyzed):

| Query | Time |
|---|---|
| Blocks whose internal point lies in two places or two county subdivisions of their county | 4.5 s, none found |
| Blocks with no county subdivision | 1.3 s, none found |
| Rollup `GROUP BY` for places / county subdivisions | 2.0 s / 2.7 s |
| Statuses of the release outside every place (one aggregate) | 1.4 s |
| `statuses_in` with the full-data suite's aggregate, every place | 25.9 s for 1,265 areas; slowest 0.42 s (Columbus) |
| The same, every county subdivision | 34.4 s for 1,597 areas; slowest 0.42 s (Columbus) |
| Full-data geometric check (decision 9), places / county subdivisions | 37.6 s / 60.1 s |

Every area's selected statuses matched its grouped counts.

**The real load with this change,** from the lines it prints:

| Step | Time |
|---|---|
| Block assignment: both checks and the `UPDATE` | 35 s |
| Place rollups | 2 s |
| County subdivision rollups | 3 s |
| **Whole load** | **494 s** |

- The whole load took 494 s, against 432 s in 0009. The assignment and the two
  new levels account for 40 s of the 62 s difference. The load does not time
  the other steps this change touches: the analysis of the block table, and the
  foreign-key check, which now also covers the blocks' two new columns. Part of
  the difference is variation between runs: writing the census blocks took
  170 s here and 165 s in 0009.
- The load printed `block assignment: 155,805 of 276,428 blocks in a place`, and
  built 1,265 place rows summing to 3,024,507 locations and 1,597
  county-subdivision rows summing to 4,542,350.
- `build_rollups` rebuilt all 378,741 rows in 54 s, container start included.
- After the load, `geography_block` takes 645 MB on disk, against 350 MB before
  this change. The `UPDATE` writes a second version of every block row.
  Autovacuum frees the old versions for reuse once the load commits, but the
  table keeps its size until the next load's `TRUNCATE`.
- `served_unserved_rollup` still takes 68 MB with its indexes.

## Alternatives considered

- **A separate assignment table.** It fills in 7 s rather than 27 s and
  `NOT NULL` is enforced, but every place and county-subdivision query joins one
  more table, and that grouping failed at the stock 64 MB `/dev/shm`.
- **Assigning by largest overlap.** The same result for every Ohio block, at
  about 98 s rather than 2.5 s. The full-data suite uses it as its check.
- **The Census Bureau's block assignment files.** They are authoritative and
  free of geometry, but they are another download, while the spatial join needs
  only the boundary files already loaded.
- **`ST_Contains`.** A point on a shared boundary would match neither area and
  go unreported.
- **The ORM's subquery per block.** It took 63 s.
- **Writing each block with its areas in one pass,** through a staging table and
  `INSERT … SELECT`. One write of the block table, and `NOT NULL` would be
  possible, at the cost of a staging table and a different load order for the
  boundaries. Not measured end to end.
- **Tallying each place's counts from the CSV in every load.** The CSV has no
  place column, and tallying per block was already rejected in 0009 (42 s per
  load).
- **A command that only reassigns blocks.** Reviewers start from an empty
  database, and `build_rollups` refuses instead of building wrong rows.

## Consequences

- **Positive:** #3 and #26 can serve places and county subdivisions with the
  same area keys as every other level, and select an area's locations through an
  index.
- **Positive:** The assignment is checked in every load, and geometrically in
  the full-data suite.
- **Negative:** Each data load takes about a minute longer: 494 s against
  432 s, 35 s of it the block assignment.
- **Negative:** The block table takes 645 MB on disk after a load, against
  350 MB, until the next load truncates it.
- **Negative:** `county_subdivision` is nullable in the schema. Only the load's
  check keeps it filled.
- **Negative:** The place totals check confirms the grouping, not the
  assignment.
- **Negative:** A database loaded before this change needs a full data load.
  `build_rollups` refuses to run until then.
- **Follow-up:** The database container's 64 MB `/dev/shm` can fail any large
  parallel hash join. Raising it is infrastructure work, outside this issue.
