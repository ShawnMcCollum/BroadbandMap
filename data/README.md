# Data

Data files are not committed to this repository. Everything in `data/`
except this README is ignored by Git. Download the files below into
`data/raw/` before loading the database.

When you are done, the folder looks like this:

```text
data/raw/
├── bdc_39_fixed_broadband_served_unserved_D25_29sep2026.zip
└── tiger2020/
    ├── tl_2020_us_state.zip
    ├── tl_2020_us_county.zip
    ├── tl_2020_39_tract.zip
    ├── tl_2020_39_bg.zip
    ├── tl_2020_39_tabblock20.zip
    ├── tl_2020_39_place.zip
    └── tl_2020_39_cousub.zip
```

Once the files are in place, load them as described in
[Load the Ohio data](../README.md#load-the-ohio-data).

## 1. FCC Served/Unserved data for Ohio

The FCC download is behind a web form, so it is downloaded by hand.

1. Open the FCC National Broadband Map data download page for the
   December 2025 release:
   <https://broadbandmap.fcc.gov/data-download/nationwide-data?version=dec2025&pubDataVer=dec2025>
2. Check that **Availability Data As Of** shows **Dec 31, 2025**.
3. Under **State**, select **Ohio**.
4. In the **Served/Unserved** table, click **Download**.
5. Save the zip, unopened, to `data/raw/`.

The file is named
`bdc_39_fixed_broadband_served_unserved_D25_29sep2026.zip`. The FCC calls this
the December 2025 release; the `29sep2026` in the name is the date the FCC
processed it.

| | |
|---|---|
| **Source** | Federal Communications Commission, Broadband Data Collection |
| **Vintage** | December 2025 release (filing period `D25`) |
| **License** | Public data released by a U.S. government agency |

## 2. Census boundary files

The FCC file has no geometry, so boundaries come from the U.S. Census Bureau's
TIGER/Line Shapefiles. The reasons for this choice are in
[ADR 0005](../docs/decisions/0005-census-tiger-2020-boundaries.md).

A script downloads them. From the repository root, run:

```powershell
docker compose run --rm --no-deps backend python scripts/fetch_boundaries.py
```

The default download is about 410 MB, mostly census blocks. Files already
downloaded are skipped, so the script can be rerun after an interruption.

To also download ZIP Code Tabulation Areas (one nationwide file, about
528 MB), add `--include-zcta`:

```powershell
docker compose run --rm --no-deps backend python scripts/fetch_boundaries.py --include-zcta
```

| Geography | File | Size |
|-----------|------|------|
| State | [`tl_2020_us_state.zip`](https://www2.census.gov/geo/tiger/TIGER2020/STATE/tl_2020_us_state.zip) | 10 MB |
| County | [`tl_2020_us_county.zip`](https://www2.census.gov/geo/tiger/TIGER2020/COUNTY/tl_2020_us_county.zip) | 81 MB |
| Census tract | [`tl_2020_39_tract.zip`](https://www2.census.gov/geo/tiger/TIGER2020/TRACT/tl_2020_39_tract.zip) | 9 MB |
| Block group | [`tl_2020_39_bg.zip`](https://www2.census.gov/geo/tiger/TIGER2020/BG/tl_2020_39_bg.zip) | 19 MB |
| Census block | [`tl_2020_39_tabblock20.zip`](https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/tl_2020_39_tabblock20.zip) | 280 MB |
| Place | [`tl_2020_39_place.zip`](https://www2.census.gov/geo/tiger/TIGER2020/PLACE/tl_2020_39_place.zip) | 4 MB |
| County subdivision | [`tl_2020_39_cousub.zip`](https://www2.census.gov/geo/tiger/TIGER2020/COUSUB/tl_2020_39_cousub.zip) | 6 MB |
| ZIP Code Tabulation Area (opt-in) | [`tl_2020_us_zcta520.zip`](https://www2.census.gov/geo/tiger/TIGER2020/ZCTA520/tl_2020_us_zcta520.zip) | 528 MB |

State and county files cover the whole country; the loader keeps only Ohio.

| | |
|---|---|
| **Source** | U.S. Census Bureau, TIGER/Line Shapefiles |
| **Vintage** | 2020, matching the census blocks in the FCC data |
| **License** | Public domain (U.S. government work) |

H3 hexagon boundaries are computed from the FCC file's `h3_res8_id` column, so
they need no download.
