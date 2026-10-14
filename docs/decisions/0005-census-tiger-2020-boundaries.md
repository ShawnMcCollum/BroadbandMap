# 0005 — Census TIGER/Line 2020 for boundary geometries

- **Status:** Accepted
- **Date:** 2026-10-14

## Context

The FCC Served/Unserved file has no geometry. Each location carries only a
2020 census block GEOID (`block_geoid`) and an H3 resolution-8 cell
(`h3_res8_id`). Mapping or summarizing by any area other than an H3 cell needs
boundary polygons from another source
([#9](https://github.com/ShawnMcCollum/BroadbandMap/issues/9)).

The loader ([#2](https://github.com/ShawnMcCollum/BroadbandMap/issues/2))
decides which geographies are loaded and shown. This decision covers only
**getting the boundary data**. Raw files are easy to load later; adding a new
source later means new research, new download steps and new documentation.
So every geography that could reasonably be useful is fetched now, and the
loader limits what it uses.

## Decision

Boundaries come from the U.S. Census Bureau's **TIGER/Line Shapefiles, 2020
vintage**. The 2020 vintage matches the census blocks the FCC uses for
`block_geoid`, so GEOIDs join without translation. TIGER/Line is preferred
over the simplified cartographic boundary files because it carries full-detail
geometry for every level, including blocks.

Files are fetched from
<https://www2.census.gov/geo/tiger/TIGER2020/> by
`backend/scripts/fetch_boundaries.py` into `data/raw/tiger2020/`.

| Geography | File | Size | Joins to locations by |
|-----------|------|------|-----------------------|
| State | `STATE/tl_2020_us_state.zip` (nationwide) | 10 MB | `block_geoid` digits 1–2 |
| County | `COUNTY/tl_2020_us_county.zip` (nationwide) | 81 MB | `block_geoid` digits 1–5 |
| Census tract | `TRACT/tl_2020_39_tract.zip` | 9 MB | `block_geoid` digits 1–11 |
| Block group | `BG/tl_2020_39_bg.zip` | 19 MB | `block_geoid` digits 1–12 |
| Census block | `TABBLOCK20/tl_2020_39_tabblock20.zip` | 280 MB | `block_geoid` |
| Place (cities, villages) | `PLACE/tl_2020_39_place.zip` | 4 MB | Spatial join |
| County subdivision (townships) | `COUSUB/tl_2020_39_cousub.zip` | 6 MB | Spatial join |
| ZIP Code Tabulation Area | `ZCTA520/tl_2020_us_zcta520.zip` (nationwide) | 528 MB | Spatial join; **opt-in** |

- **State and county** are published only as nationwide files. The loader
  filters them to Ohio (`STATEFP = '39'`).
- **ZCTAs** are published only as a single nationwide file, which would more
  than double the download. They are fetched only when the script is run with
  `--include-zcta`.
- **H3 cells** are computed in Python from `h3_res8_id` and need no download.

### License

TIGER/Line files are produced by the U.S. Census Bureau, a U.S. government
agency, and are in the public domain. The project cites the source in
[`data/README.md`](../../data/README.md).

### Storage

No data file is committed: `data/` is excluded by `.gitignore`, except for its
README. Each reviewer runs the fetch script, so Git LFS is not needed. The
default download is about 410 MB of disk on the reviewer's machine.

## Alternatives considered

- **Cartographic boundary files.** Smaller and pre-simplified for display, but
  they are not published at block level, and simplified shapes would be a
  poor base for spatial joins. Display simplification can be done in PostGIS
  later if needed.
- **Fetch only what the first map uses (counties).** Smallest download, but
  each later geography would repeat the sourcing work.
- **Commit the files with Git LFS.** Avoids a download step, but adds a tool
  and storage quota for data the Census Bureau already hosts reliably.

## Consequences

- **Positive:** Every geography the map is likely to use has a documented,
  reproducible source, and all of them share one vintage.
- **Positive:** The fetch step needs only Docker, like the rest of the project.
- **Negative:** The default download is about 410 MB, most of it census
  blocks, even though the first map shows only counties.
- **Negative:** The download depends on the Census Bureau's server being
  available. The script can be rerun and skips files already fetched.
- **Follow-up:** #2 decides which geographies the loader populates. The first
  visualization is a county-level rollup.
