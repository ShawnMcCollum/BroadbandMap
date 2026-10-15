# 0008 — Served/Not served rollups by geography

- **Status:** Accepted
- **Date:** 2026-10-14
- **Amended by:** [0009](0009-rollups-for-finer-levels.md), which adds the tract, block group, block and H3 levels

## Context

A *rollup* is one row of Served/Not served counts for one area in one
release. An *area key* is the pair (level, code) that names an area, for
example (`county`, `39049`) for Franklin County.

[#10](https://github.com/ShawnMcCollum/BroadbandMap/issues/10) keeps every
location ([open question 5](../open-questions.md#data-and-domain)) and asks
for summary views whose areas lead to the locations behind them.
[#22](https://github.com/ShawnMcCollum/BroadbandMap/issues/22) builds the
summaries, and [#26](https://github.com/ShawnMcCollum/BroadbandMap/issues/26)
builds the drill-down from an area to its locations.

Computing a county rollup on request scans all 4,542,350 statuses and takes
2.0 s, for every map or dashboard view. The data places a location only by its
block GEOID and its H3 cell
([0006](0006-data-model-for-locations-and-boundaries.md)), so a rollup by
area has to be derived from one of those two columns.

The loader that fills the tables is described in
[0007](0007-loading-and-verifying-the-source-data.md).

## Decision

1. **Rollups are stored in a table, `served_unserved.Rollup`.** A county
   rollup computed per request scans all 4.5M statuses and takes 2.0 s for
   every map or dashboard view. A stored row is an index lookup.
2. **Every data load rebuilds the rollups inside its transaction.** The loader
   calls `build_rollups(release)` once the statuses are written, before the
   foreign-key check and reconciliation, which adds about 10 s. The foreign-key
   check then covers the rollups too. The rollups can never disagree with the
   statuses, and a failed load keeps the previous rollups. The rollup table is
   one of the tables the loader owns, so the load's `TRUNCATE` covers eleven
   tables. It has to: a table with a foreign key to `bdc_release` blocks a
   `TRUNCATE` of `bdc_release` unless it is truncated in the same statement.
3. **One table holds every level, keyed by release, level and code.** A
   rollup has the same columns at every level, so a new level adds a choice
   and a GEOID length, not a table. There is no foreign key to a boundary
   table, because the H3 level has no table. A check constraint requires the
   code to have the right form for its level.
4. **The area key selects its statuses.** For census levels, the code is the
   area's GEOID, and a location lies in the area when its block GEOID starts
   with the code. `statuses_in(release, level, code)` is the one function that
   turns a key into the statuses its row counts, and #26 builds on it. It uses
   `location__block__geoid__startswith`, which Django turns into
   `block_id::text LIKE '39049%'`, served by the `varchar_pattern_ops` index
   that Django creates on `bdc_location.block_id`. The keys for every level are
   in the table below.
5. **County is the only level built now.** This is what #22 asks for. Finer
   levels move to a follow-up issue,
   [#28](https://github.com/ShawnMcCollum/BroadbandMap/issues/28). There is no
   state row; the statewide total is the sum of the county rows.
6. **Rows hold counts, not shares.** A row holds `locations` and the served
   count for each of the three flags, so the API can offer any flag. Wired is
   the default ([open question 1](../open-questions.md#data-and-domain)). Not
   served is `locations` minus served. Shares are computed by whoever displays
   them: counts add up across areas and releases, but shares do not, and
   storing a share would fix a rounding choice in the data.
7. **Only areas with at least one location get a row,** enforced by
   `locations >= 1`. An area without locations has no Served/Not served share.
   The API ([#3](https://github.com/ShawnMcCollum/BroadbandMap/issues/3))
   starts from the boundary table and shows such areas as having no
   locations. All 88 Ohio counties have locations.
8. **Constraints mirror the flag nesting,** as in 0006: wired ≤ terrestrial ≤
   any ≤ locations. Each area also appears once per release, and its code must
   fit its level.
9. **Every data load reconciles the county rollups against counts tallied
   from the CSV.** The `Counts` of a load gain a `county_rollups` section with
   keys like `"39055:wired_100_20"`, a county GEOID, a colon and a count name.
   The tally adds about 8 s to the CSV read. The full-data suite compares the
   rollups with an independent CSV reader, and checks that each county's key
   selects exactly the statuses its row counts.
10. **A `build_rollups` management command** rebuilds the rollups of every
    loaded release from the loaded statuses, in about 2 s. A database loaded
    before this change, or one that gains a new level, then needs no
    six-minute reload.
11. **The admin is read-only for `Rollup`,** as for every model (0006,
    decision 7). Search is an exact match on the code.
12. **Rollups count every status, suspect or not.** How rollups treat flagged
    rows is decided in
    [#24](https://github.com/ShawnMcCollum/BroadbandMap/issues/24).

The area keys, built now and later:

| Level | Code | A location is in the area when | Status |
|---|---|---|---|
| county | 5-digit GEOID | its block GEOID starts with the code | built |
| tract | 11-digit GEOID | its block GEOID starts with the code | later |
| block group | 12-digit GEOID | its block GEOID starts with the code | later |
| block | 15-digit GEOID | its block GEOID equals the code | later |
| H3 resolution 8 | 15-character cell index | its `h3_res8` equals the code | later |
| place, county subdivision | 7- / 10-digit GEOID | needs a block-to-area assignment first (not a GEOID prefix of the block) | later |

A prefix match must use `startswith`, which becomes `LIKE 'code%'` and is
served by the index. A string range is not a prefix test in the database's
`en_US.utf8` collation: `block_id >= '39049' AND block_id < '3904:'` matched
no rows, although Franklin County has 379,790 locations. Code must never use
a range to select an area's locations.

Measured on the December 2025 Ohio data, in a development database running
PostgreSQL 17.5 with default settings:

| Operation | Time |
|---|---|
| County rollup, one `GROUP BY` over statuses joined to locations | 2.0 s |
| The same for tract / block group / block / H3 cell | 4.7 / 4.5 / 5.5 / 5.0 s |
| All six levels in one `GROUPING SETS` query | 43 s |
| One county's statuses by GEOID prefix: Franklin (379,790) / a typical county | 0.7 s / 35 ms |
| Reading the FCC CSV with the loader's current tally / also tallying four served counts per county | 34 s / 42 s |
| Building the county rollups inside a full data load | 10 s |

Inside a data load, building the rollups took 10 s rather than 2 s, most
likely because it is the first read of 4.5M statuses written moments before,
with no planner statistics on them yet. A data load takes about 18 s longer: 10 s to build the
rollups and 8 s to tally the CSV.

## Alternatives considered

- **Aggregating on every request.** Nothing to store or keep in step, but
  every view costs 2 s.
- **A PostgreSQL materialized view, refreshed by the load.** Django's
  migrations do not track it, so changing a column it reads needs
  hand-written SQL migrations.
- **One table per level, with a real foreign key to its boundary.** The
  tables would have identical columns, and the H3 level has no boundary
  table.
- **A county column on `Location`.** A query still aggregates 4.5M rows per
  request, and the table would need one column per level.
- **Storing shares instead of counts.** A share cannot be added across areas
  or releases, and it fixes a rounding choice in the data.
- **Rows for areas with no locations.** Such an area has no share to show,
  and the boundary table already lists it.
- **Building every level now.** Block and H3 alone add 363,170 rows and at
  least 10 s to each load, with no consumer yet.
- **Writing the rollups from the loader's Python tally of the CSV.** The
  rollups would then derive from the file, not the database, and could not be
  rebuilt without it.
- **All levels in one `GROUPING SETS` query.** It takes 43 s, against 4.5 to
  5.5 s for each level on its own, because its sorts spill to disk at the
  default 4 MB `work_mem`.

## Consequences

- **Positive:** Summary reads are index lookups, and always match the loaded
  statuses.
- **Positive:** The area key gives #26 its drill-down rule, and it is tested
  against every county.
- **Positive:** A level is added with one choice and one GEOID length, and
  `build_rollups` fills it without a reload.
- **Negative:** Each data load takes about 18 s longer.
- **Negative:** Only the loader and `build_rollups` write rollups, so statuses
  changed any other way leave them stale until `build_rollups` runs.
- **Negative:** Suspect rows are counted like any other until #24 decides
  otherwise.
- **Follow-up:** Rollups for the finer levels
  ([#28](https://github.com/ShawnMcCollum/BroadbandMap/issues/28)), the API
  (#3) and the drill-down (#26).
