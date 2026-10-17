# 0023 — Status admin searches a block or a cell in every release

- **Status:** Accepted
- **Date:** 2026-10-16
- **Related:** [0012](0012-location-placement-per-release.md), [0019](0019-location-cursors.md), [0021](0021-indexes-only-where-queries-read.md), [0022](0022-status-admin-pages-read-an-index.md), [#51](https://github.com/ShawnMcCollum/BroadbandMap/issues/51)

## Context

Before [0012](0012-location-placement-per-release.md), the admin's list of
locations found a location by its ID, its block GEOID or its H3 cell. Since
then, each served status holds its location's block and cell in its release,
and the location model is gone. The served-status admin searched by location
ID only, so an administrator could not list the statuses in a block or a cell.

The statuses' block and cell are indexed only after the release:
`servedstatus_release_block` on `(release_id, block_id)` and
`servedstatus_release_h3` on `(release_id, h3_res8)`. PostgreSQL 17 has no
skip scan, so a condition on the second column alone reads a whole index.
The search by location ID already names every release, `release_id IN (…)`,
for the unique `(release, location_id)` index
([0021](0021-indexes-only-where-queries-read.md), decision 1).

The three kinds of term have distinct forms in the loaded data:

- All 9,095,317 location IDs have 10 digits, from 1000338835 to 1687416096.
- A block GEOID has 15 digits.
- An H3 resolution-8 cell index has 15 lowercase hex characters. It always
  ends in `fffff`, since its unused finer-resolution digits are all set.

In Ohio, a block holds a median of 11 statuses in a release and at most 807.
A cell holds a median of 7 and at most 1,302.

## Decision

1. **A term of 15 digits is a block GEOID, one of 15 lowercase hex characters
   is an H3 cell index, and any other decimal term is a location ID.**
   - The block and cell forms are those of their rollup codes, from
     `AREA_KEYS`. The search selects the statuses through the same lookups as
     `statuses_in`.
   - A block GEOID is tried first, since its digits are also hex. No location
     ID has 15 digits, and every cell index has a letter, so no term can be
     read two ways.
   - The match is exact. A county's or a tract's GEOID is read as a location
     ID and finds nothing. A cell index in capitals finds nothing, as in the
     rollup admin and the API, which also take only the stored lowercase form.
2. **Every search names every release,** `release_id IN (…)`, with or
   without a release filter. The block and cell indexes then find the area
   with one descent per release. A release filter adds `release_id = <id>`,
   and the index reads that release only.
3. **The search help names the three forms:** "Location ID, block GEOID
   (15 digits) or H3 cell index (15 lowercase hex characters)".
4. **A term in none of these forms finds nothing** without reading the
   releases.

Results follow the list's order, release ID then location ID, and its count
stops at 10,000 statuses ([0022](0022-status-admin-pages-read-an-index.md)).

## Measurements

Measured on the development database with Ohio's December 2025 and June 2025
releases, 9,095,317 statuses, PostgreSQL 17.5. Each page was built and
rendered in-process for a superuser, as the admin does. Render times are
medians of three runs after a warm-up. Query times are from
`EXPLAIN ANALYZE`. Block searches read `servedstatus_release_block`, cell
searches `servedstatus_release_h3` and the location search the unique
index. Each count was an index-only scan.

| Search | Releases | Found | Page render | Count query | Page query |
|---|---|---:|---:|---:|---:|
| Block 391590505011009, the largest | Both | 1,614 | 46 ms | 0.37 ms | 1.02 ms |
| Block 391590505011009, page 2 | Both | 1,614 | 52 ms | 0.36 ms | 0.67 ms |
| Block 391590505011009 | December 2025 | 807 | 57 ms | 0.27 ms | 0.58 ms |
| Block 390017701001005, of median size | Both | 22 | 19 ms | 0.06 ms | 0.10 ms |
| Block 390017701001005 | December 2025 | 11 | 15 ms | 0.06 ms | 0.08 ms |
| Block 391599999999999, no statuses | Both | 0 | 11 ms | 0.09 ms | 0.04 ms |
| Cell 882a930f45fffff, the largest | Both | 2,584 | 47 ms | 0.59 ms | 0.99 ms |
| Cell 882a930f45fffff | December 2025 | 1,282 | 48 ms | 0.37 ms | 0.78 ms |
| Cell 8827492003fffff, of median size | Both | 14 | 17 ms | 0.06 ms | 0.06 ms |
| Cell 8827492003fffff | December 2025 | 7 | 16 ms | 0.05 ms | 0.06 ms |
| Cell 8828308281fffff, no statuses | Both | 0 | 11 ms | 0.08 ms | 0.03 ms |
| Location 1000338835 | Both | 2 | 12 ms | 0.06 ms | 0.12 ms |

With a filter as well:

- The largest cell, filtered to December 2025 statuses without wired
  service, found none in 11 ms. The count read the cell's 1,282 index
  entries and filtered them: 0.26 ms.
- The largest block, in both releases, filtered to statuses not served by
  any technology, found none in 11 ms. The planner read
  `servedstatus_not_served` instead, 294 entries: 0.28 ms.

Without the release list, the counts for the largest block and cell read
all of `servedstatus_release_block` (104 MB) and `servedstatus_release_h3`
(94 MB). Over four runs the medians were 118 ms and 106 ms, after first runs
of 649 ms and 187 ms.

Before this decision, a block term was read as a location ID, and a cell
term matched nothing. Both found nothing.

## Alternatives considered

- **Search a block or a cell only within a selected release,** as
  [#51](https://github.com/ShawnMcCollum/BroadbandMap/issues/51) first
  scoped it. With the release list, a search of both releases took at most
  1.02 ms per query, so a filter need not be required.
- **Search without the release list.** Each query reads a whole index:
  over 100 ms for two releases, and more with every state and release.
- **An index on `block_id` or `h3_res8` alone.** Every data load would
  maintain it, for searches that the release list already serves.
  [0021](0021-indexes-only-where-queries-read.md) dropped the `location_id`
  index, 194 MB for two releases, for the same reason.
- **Read a 15-digit term as a location ID as well.** Every block search
  would add an `OR` for location IDs, and the FCC's location IDs have
  10 digits.
- **Accept a cell index in capitals** by lowercasing the term. The rollup
  admin and the API take only the lowercase form, and the admin keeps to it.

## Consequences

- **Positive:** The admin lists the statuses in a block or a cell, in every
  release or in one, in milliseconds, through the existing indexes. No index
  or migration is added.
- **Positive:** The admin, the rollups and the API share one definition of a
  block's and a cell's code, `AREA_KEYS`.
- **Negative:** A search descends an index once for each release loaded. Its
  cost grows with the number of releases, not with their size.
- **Negative:** A 15-digit location ID would be read as a block GEOID. None
  exists.
- **Negative:** The admin finds no area larger than a block. The statuses of
  a county, a tract or a place are listed by the location drill-down
  ([0019](0019-location-cursors.md)).
