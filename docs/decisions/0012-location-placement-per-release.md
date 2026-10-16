# 0012 — A location's block and H3 cell are stored per release

- **Status:** Accepted
- **Date:** 2026-10-15
- **Amended by:** [0021](0021-indexes-only-where-queries-read.md), which drops the `location_id` index
- **Follow-up:** [#46](https://github.com/ShawnMcCollum/BroadbandMap/issues/46) implements this decision

## Context

A location's *placement* is its 2020 census block and its H3 resolution-8 cell.
The FCC file gives both on every row (`block_geoid`, `h3_res8_id`), and both
follow from the location's position in that filing period's Fabric. The other
terms are those of [0008](0008-served-not-served-rollups.md) and
[0010](0010-place-and-county-subdivision-rollups.md). A *rollup* is one row of
Served/Not served counts for one area in one release. An *area key* is the pair
(level, code) that names an area, for example (`county`, `39049`) for Franklin
County. The same key selects the locations behind the row.

[0006](0006-data-model-for-locations-and-boundaries.md) decision 5 stores
placement once per location, on `bdc.Location`, because a location's block and
H3 cell "rarely change between filing periods". It stores status per `Release`,
on `ServedStatus`.

The data-layer review
([#38](https://github.com/ShawnMcCollum/BroadbandMap/issues/38), finding H3)
found the consequence. With one shared row, loading a second release overwrites
the first release's placement, and `build_rollups`, which rebuilds every
release, then changes the first release's counts.
[#40](https://github.com/ShawnMcCollum/BroadbandMap/issues/40) asks for a data
model in which loading a second release cannot change the first release's
rollups.
[#41](https://github.com/ShawnMcCollum/BroadbandMap/issues/41) (release-scoped
loading) depends on this decision.

**How a second release was compared.** The June 2025 Ohio Served/Unserved file,
`bdc_39_fixed_broadband_served_unserved_J25_01oct2026.zip`, was downloaded from
the same FCC page as the December 2025 file, with **Availability Data As Of**
set to **Jun 30, 2025**. It was copied into the development database inside a
transaction that was rolled back, and compared with the loaded December 2025
(D25) data. Nothing was kept.

**June 2025 (J25) against December 2025 (D25),** Ohio:

| | Count |
|---|---|
| J25 locations | 4,552,967 |
| D25 locations | 4,542,350 |
| In both | 4,521,314 (99.3% of J25) |
| In J25 only (not in D25) | 31,653 |
| In D25 only | 21,036 |
| In both, placement changed | **277**: 51 block only, 222 cell only, 4 both |
| … of which changed county / tract / block group | 0 / 3 / 5 |
| … of which changed place / county subdivision | 12 / 12 |
| In both, wired 100/20 flag changed | 50,419 (1.1%) |
| J25 rows the loader would reject (unknown block, bad cell, flags not nested) | 0 |

**J25 rollup rows that would change if D25's placement replaced J25's,** which
is what one shared `Location` row per location does:

| Level | Rows changed | Of rows | Largest change |
|---|---|---|---|
| county | 0 | 88 | — |
| tract | 6 | 3,162 | 1 location |
| block group | 10 | 9,459 | 1 |
| block | 104 | 235,644 | 3 |
| H3 cell | 419 | 127,836 | 2 |
| place | 8 | 1,265 | 2 |
| county subdivision | 15 | 1,597 | 3 |
| **Total** | **562** | 379,051 | |

Two findings matter beyond the counts:

- Placement changes are rare (0.006% of locations), but they do happen. 0006's
  "rarely change" holds; "never change" does not, and the "Done when" of #40
  requires that one release's rollups never change because of another.
- **J25 was processed on 1 October 2026, two days after D25 (29 September
  2026).** The FCC reprocesses an older period after a newer one, so the order
  releases are loaded in is not the order of their periods. Any "latest wins"
  rule would have to say latest by what, and loading J25 after D25 would
  overwrite D25's placement with J25's.

## Decision

1. **A location's block and H3 cell are stored on its `ServedStatus` row, per
   release.**
   - `block`:
     `ForeignKey("geography.Block", on_delete=models.PROTECT, related_name="served_statuses", db_index=False)`,
     help text "2020 census block containing the location in this release
     (block_geoid)."
   - `h3_res8`: `CharField(max_length=15)`, help text "H3 resolution-8 cell
     index of the location in this release, lowercase hex (h3_res8_id)." The
     format check moves from `Location` and is renamed
     `served_unserved_h3_res8_format`, following the app's other constraint
     names.
   - A release's rollups and drill-down then depend only on that release's
     rows. Loading, reloading or deleting another release cannot change them,
     in whatever order releases are loaded.
2. **`bdc.Location` is removed.**
   - `ServedStatus.location` (a foreign key) becomes
     `location_id = BigIntegerField(db_index=True)`, help text "FCC location ID
     from the Broadband Serviceable Location Fabric." The column keeps its name
     and data.
   - `served_unserved_unique_location_per_release` stays.
   - Its `db_index=True` keeps the current 97 MB index, which serves the
     admin's search by location ID and lookups of one location across
     releases. Whether to keep it stays with
     [#43](https://github.com/ShawnMcCollum/BroadbandMap/issues/43).
   - *Amended by [0021](0021-indexes-only-where-queries-read.md):* the index is dropped. A search for one location names every release, and the unique index finds it with one probe per release.
   - `Location` held nothing but placement, and every reader reaches it through
     a status. Without it, a load reads the CSV once instead of twice, writes
     one 4.5M-row table instead of two and checks one 4.5M-row foreign key
     fewer, and [#41](https://github.com/ShawnMcCollum/BroadbandMap/issues/41)'s
     release-scoped load has no shared location rows to upsert.
3. **Area keys select through the status row.**
   - In `AREA_KEYS`, `location__block__geoid` becomes `block__geoid`,
     `location__h3_res8` becomes `h3_res8`, and `location__block__place` /
     `location__block__county_subdivision` become `block__place` /
     `block__county_subdivision`.
   - Prefix levels keep `startswith`. The rule in 0008 that a string range is
     never a prefix test still applies.
4. **Two explicit indexes serve the area keys:**
   - `Index(fields=["release", "block"], opclasses=["int8_ops", "varchar_pattern_ops"], name="servedstatus_release_block")`
   - `Index(fields=["release", "h3_res8"], name="servedstatus_release_h3")`
   - Every area query filters on the release, so the release leads. A
     pattern-ops index also serves `=`, so the block index covers the prefix
     levels, the block level and the place and county-subdivision joins.
   - These replace the four block and cell indexes on `bdc_location` (190 MB).
     Their names stay within Django's 30-character limit for index names.
5. **Blocks keep their place and county subdivision (0010).** Both come from
   the 2020 boundaries, which do not change between releases, so the
   block-to-area assignment is not versioned.
6. **H3 stays a 15-character string.** Storing it as a 64-bit integer
   ([#38](https://github.com/ShawnMcCollum/BroadbandMap/issues/38), L1) would
   halve the column but change the API's and the rollup codes' representation.
   It is out of scope here.

## Measurements

Measured on the December 2025 Ohio data in the development database,
PostgreSQL 17.5 with default settings and a 256 MB `/dev/shm`
([0011](0011-database-shared-memory.md)). A copy of the statuses with
`block_id` and `h3_res8` added was built inside a transaction that was rolled
back, indexed, analyzed and queried next to the current tables. These are
single runs, so the timings are indicative;
[#46](https://github.com/ShawnMcCollum/BroadbandMap/issues/46) measures them
again.

**Grouping and area selection:**

| | Current (status joined to location) | Placement on the status row |
|---|---|---|
| County rollup grouping | 1.70 s | 0.57 s |
| Block rollup grouping | 3.02 s | 1.89 s |
| Place rollup grouping (joins blocks either way) | 1.73 s | 0.81 s |
| Franklin County's 379,790 statuses by GEOID prefix | 719 ms | 67 ms |

**Table and index sizes:**

| Storage, one release | Current | Placement on the status row, no `Location` |
|---|---|---|
| `bdc_location` (heap + 5 indexes) | 584 MB | — |
| `served_unserved_servedstatus` heap | 261 MB | 404 MB |
| Status indexes: primary key, unique `(release, location)`, `location_id` | 331 MB | 331 MB |
| New: `(release_id, block_id varchar_pattern_ops)` | — | 39 MB |
| New: `(release_id, h3_res8)` | — | 36 MB |
| **Total** | **1,176 MB** | **810 MB** |

- The two new indexes are small because PostgreSQL's B-tree deduplication folds
  the repeated `(release, block)` and `(release, cell)` keys.
- Each further release adds about 810 MB under this decision, against about
  592 MB if the current shared-`Location` data model could hold several
  releases. The two are about equal at three releases. All eight periods
  published so far would take about 6.5 GB against about 5.3 GB.

## Alternatives considered

- **One shared `Location` row, latest placement wins.** Least storage when
  there are many releases. But the 562 J25 rollup rows above would change when
  D25 loads, "latest" is ambiguous because J25 was processed after D25, and the
  loader would need an upsert.
- **Latest placement wins, with older releases' rollups frozen.** The counts
  would stop changing, but `build_rollups` could no longer rebuild an old
  release, a new level could never be added to one, and
  [#26](https://github.com/ShawnMcCollum/BroadbandMap/issues/26)'s drill-down
  for an old release would list locations by the latest placement, which
  disagrees with its frozen counts. That breaks the rule of
  [#10](https://github.com/ShawnMcCollum/BroadbandMap/issues/10) that a summary
  row leads to exactly the locations behind it.
- **A per-release placement table in `bdc`** (release, location, block, cell),
  shared by later data categories. It keeps the idea in 0006 that releases and
  locations belong to the Broadband Data Collection as a whole, but keeps the
  current join on every rollup and drill-down and adds about 584 MB per release
  on top of the statuses.
  [0001](0001-start-with-ohio-served-unserved.md) gives each new data category
  its own decision, and that decision can factor placement out of
  `ServedStatus` if a second category needs it.
- **A placement table per filing period (per Fabric version), shared by the
  reprocessed versions of that period.** Less duplication, but it assumes
  placement never changes between two processings of one period, which cannot
  be checked with one processing of each. It also keeps the join and adds a
  period key.
- **Keeping `Location` as an ID registry** (location ID only, about 255 MB). A
  foreign-key target for later categories, but the load still reads the CSV
  twice and [#41](https://github.com/ShawnMcCollum/BroadbandMap/issues/41)
  must upsert IDs. Its foreign key only proves that the loader wrote both rows
  from the same file.

## Consequences

- **Positive:** A release's rollups and drill-down can never be changed by
  another release (the "Done when" of
  [#40](https://github.com/ShawnMcCollum/BroadbandMap/issues/40)), whatever the
  load order.
- **Positive:** Rollup grouping and area selection skip a 4.5M-row join. The
  measured speed-ups are in the Measurements tables.
- **Positive:** A load reads the FCC CSV once and writes one large table
  instead of two. It is expected to be shorter;
  [#46](https://github.com/ShawnMcCollum/BroadbandMap/issues/46) measures it.
- **Positive:** [#41](https://github.com/ShawnMcCollum/BroadbandMap/issues/41)
  becomes simpler. A release is its statuses and its rollups; only boundaries
  are shared between releases.
- **Negative:** Placement is stored again for every release, about 143 MB of
  heap and 75 MB of index per release. It costs more than a shared table from
  about three releases on.
- **Negative:** `bdc` no longer holds a location entity for later data
  categories to share. 0006 decisions 5 and 6 are amended.
- **Follow-up:** #46 implements this decision: the migration, the loader
  reading the CSV once, the area keys, the admin and the tests.
- **Follow-up:** For
  [#26](https://github.com/ShawnMcCollum/BroadbandMap/issues/26), each record
  (location ID, block, cell, flags) comes from one row, and the lookups are
  those of decision 3.
- **Follow-up:** For
  [#24](https://github.com/ShawnMcCollum/BroadbandMap/issues/24), the suspect
  rules being considered (water blocks, blocks without housing units) depend
  on the block, which is now per release. A suspect flag therefore belongs on
  `ServedStatus`.
- **Follow-up:** For
  [#43](https://github.com/ShawnMcCollum/BroadbandMap/issues/43), the five
  `bdc_location` indexes go away with the table. The decision on the
  `location_id` index stays.
- **Follow-up:** For #41, a release is its statuses and rollups, and only
  boundaries are shared between releases. The J25 file is a ready second
  release for its tests, and its processing date, after D25, is a case for a
  release loaded out of period order.
