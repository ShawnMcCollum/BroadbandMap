# 0007 — Loading and verifying the source data

- **Status:** Accepted
- **Date:** 2026-10-14
- **Amended by:** [0013](0013-release-scoped-data-loads.md), which makes a data load add one release beside those already loaded, instead of replacing all loaded data

## Context

A *data load* is one run of the loader: it reads the source files in
`data/raw/` and writes them into PostGIS. Starting the application loads no
data; a data load runs only when its command is run.

The Ohio Served/Unserved file has 4,542,350 rows, and the TIGER/Line files
add 276,428 census block polygons and about 15,600 polygons at the other six
levels ([0005](0005-census-tiger-2020-boundaries.md)). Every location has a
block, a status and an H3 cell, so one bad row can make the map or a rollup
wrong without any error.

[0003](0003-celery-for-background-loads.md) asks for each load to run in one
transaction, so a failed load leaves the database as it was. The tables it
fills are defined in [0006](0006-data-model-for-locations-and-boundaries.md).
This decision covers the loader
([#21](https://github.com/ShawnMcCollum/BroadbandMap/issues/21)) and how its
output is verified. The Celery task and the `LoadRun` record come later
([#15](https://github.com/ShawnMcCollum/BroadbandMap/issues/15)).

## Decision

1. **The loader is a new `etl` app,** as 0002 places the ETL in the same
   project as a Django app. It has no models of its own yet.
2. **A data load replaces all loaded data, in one durable transaction.** The
   transaction starts with one `TRUNCATE` of the ten tables the loader owns,
   then loads everything. The database holds one state and one release at a
   time. `transaction.atomic(durable=True)` makes the loader refuse to run
   inside another transaction, so a caller cannot commit only part of a load.
   While a data load runs, the rest of the application keeps running, but
   queries on the ten loaded tables wait until it commits.
3. **Python reads and validates every row, and `COPY` writes it.** Every
   table is written with `COPY`, boundaries included, with geometries sent as
   hex EWKB. A load stops at the first bad row, and the error names the file
   and the CSV line or shapefile feature. The database constraints from 0006
   stay in place as a backstop.
4. **Shapefiles are read through GDAL.** GeoDjango's `DataSource` opens the
   shapefile inside the zip, so nothing is extracted and no dependency is
   added. Each geometry is reprojected from NAD83 (EPSG:4269) to WGS84
   (EPSG:4326) and promoted to a MultiPolygon in Python, before `COPY`. Parent
   IDs come from the source's FIPS component fields (state, county, tract and
   the first digit of the block number), not from slicing the GEOID. The
   loader checks that each GEOID starts with its parent's GEOID.
5. **Indexes and foreign keys stay in place during a data load.** The
   foreign keys are deferred, so a missing parent is found when they are
   checked, before commit.
6. **The `Release` comes from the FCC file name.** In
   `bdc_39_fixed_broadband_served_unserved_D25_29sep2026.zip`, `D25` is the
   filing period (`D` is as of 31 December, `J` is 30 June), and `29sep2026`
   is the date the FCC processed it.
7. **Checks run in this order, and any failure rolls the load back:**
   1. A pre-check of every file, before the transaction opens: it exists,
      opens as a zip, passes `testzip()` and holds the expected members. A
      missing or corrupt file fails in seconds, not minutes into a load.
   2. Row validation while streaming (decision 3).
   3. A geometry validity check in PostGIS, one `ST_IsValid` query per level.
      Checking in Python would add over a minute for blocks.
   4. The foreign-key check (`SET CONSTRAINTS ALL IMMEDIATE`).
   5. Reconciliation: the loader counts what it reads (rows per table, flag
      combinations, and locations per county), counts the same things in the
      database, and raises `ReconciliationError` on any difference. Both sets
      of counts are returned in a `LoadResult` that #15 can store.
8. **Malformed rows fail the data load. Suspect rows are a follow-up.** A
   malformed row cannot be stored as it is: a flag of `2`, flags that are not
   nested, an unknown block or a bad H3 cell. The 0006 constraints reject
   these values, and a malformed row most likely means the FCC changed its
   format, so loading the rest would hide that. A suspect row is well formed
   but questionable against another source. Profiling found 45 locations in 33
   census blocks that are entirely water, and 50,177 locations (1.1%) in
   15,774 blocks with no 2020 housing units. The real files have no malformed
   rows. Flagging suspect rows needs rules, a new field and a decision on how
   the map and rollups treat them, so it is a separate issue
   ([#24](https://github.com/ShawnMcCollum/BroadbandMap/issues/24)).
9. **One management command,** `load_served_unserved [--data-dir PATH]`, with
   `/data/raw` as the default. It runs in the foreground and reports progress
   through a callback, so #15 can queue it as a Celery task and record
   progress in `LoadRun` without changing the loader.
10. **Three layers of tests verify the loader:**
    1. **Fast tests on fixtures.** The fixtures are a real slice of Ohio:
       Geauga County, one census tract with its 2 block groups and 49 blocks,
       a place and two county subdivisions (one a seven-part MultiPolygon),
       plus West Virginia and one West Virginia county to test the state
       filter. A committed script builds the shapefiles with `ogr2ogr`. The
       fixture CSV is 31 real rows from that tract, covering every flag
       combination. Malformed shapefiles are committed; malformed CSV rows
       are one-line edits of the fixture CSV in a parametrized table.
    2. **Reconciliation inside every load,** as in decision 7.
    3. **A full-data suite,** marked `full_data` and deselected by default so
       the regular checks stay fast. It loads the real files and compares the
       result with expected values read by independent readers: `csv` for the
       FCC file, and a small `struct`-based dBASE reader for the shapefile
       attribute tables. Neither shares code with the loader or with GDAL. The
       readers are themselves tested against the fixtures.

Measured full load, as one transaction into a scratch database, with every
index and foreign key in place:

| Step | Time |
|---|---|
| Boundaries (census blocks alone: 135 s) | 147 s |
| 4,542,350 locations | 70 s |
| 4,542,350 statuses | 17 s |
| Deferred foreign-key checks | 84 s |
| Reconciliation queries and block validity check | 6 s |
| Commit | < 1 s |
| **Total** | **5.4 min** |

The loaded data takes 1.6 GB: locations 584 MB, statuses 592 MB and blocks
327 MB.

## Alternatives considered

- **GeoDjango `LayerMapping`.** It saves row by row through the ORM, cannot
  build a point from two fields, and cannot filter by state.
- **`ogr2ogr` into PostGIS.** Fast, but it bypasses the Python validation and
  counting.
- **ORM `bulk_create`.** Simple, but it builds a model object for every row,
  which is slow for millions of rows, and the geometries would still need
  converting.
- **Staging tables filled by `COPY`, then SQL inserts.** The row checks would
  move into SQL, but the data would be written twice.
- **Dropping and re-adding foreign keys and indexes around the load.** It
  would save about a minute of 5.4, but it means changing constraints that
  Django's migrations own.
- **A release-scoped replace** (delete one release's statuses, upsert
  locations, keep boundaries). It is needed once a second release is loaded
  next to the first, and not before.
- **Synthetic fixtures.** Easier to make, but they would not carry the shapes
  of the real files: a seven-part MultiPolygon, or a nationwide file with
  other states in it.
- **Expected counts read through GDAL.** Quicker to write, but a mistake in
  GDAL or in the loader's use of it would then appear in both sides of the
  comparison.
- **Keeping malformed rows and flagging them as suspect,** instead of failing
  the data load. The 0006 constraints do not allow the values, so it would
  need a separate table for rejected rows. Marking a whole release as suspect
  would make every query filter on the flag.

## Consequences

- **Positive:** Loads are atomic and repeatable, and a failure names the file
  and the line.
- **Positive:** Every load proves its own counts before it commits, and the
  full-data suite checks them against readers that share no code with the
  loader.
- **Negative:** Readers of the ten loaded tables wait for about six minutes
  during a load.
- **Negative:** The database holds one state and one release at a time. A
  second release needs a release-scoped replace.
- **Negative:** The full-data suite runs two full loads and takes about 13
  minutes.
- **Follow-up:** [#15](https://github.com/ShawnMcCollum/BroadbandMap/issues/15)
  adds the Celery task and `LoadRun`. Flagging suspect rows is
  [#24](https://github.com/ShawnMcCollum/BroadbandMap/issues/24).
