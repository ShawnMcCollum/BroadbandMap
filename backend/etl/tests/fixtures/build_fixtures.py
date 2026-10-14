"""Rebuild the TIGER/Line test fixtures from the real files in /data/raw/tiger2020.

The fixtures are a real slice of Ohio:

- Geauga County (39055), census tract 3120 (39055312000) with its 2 block groups
  and 49 blocks, Parkman CDP, and Troy and Middlefield townships. Middlefield
  is a seven-part MultiPolygon.
- The state and county files also keep West Virginia and Brooke County, WV, to
  test the Ohio filter. State outlines are simplified; everything else keeps
  full detail.
- Two malformed tract files, for the tests of the loader's error messages.

The sources are public: TIGER/Line is public domain, and the FCC data is
public. Run it by hand from the repository root when the fixtures need to
change; the tests never run it:

    docker compose run --rm --no-deps backend python etl/tests/fixtures/build_fixtures.py
"""

import subprocess
import tempfile
import zipfile
from pathlib import Path

FIXTURES = Path(__file__).parent
SOURCE_DIR = "/data/raw/tiger2020"
PARTS = (".shp", ".shx", ".dbf", ".prj", ".cpg")

BAD_GEOID_SQL = (
    "SELECT STATEFP, COUNTYFP, TRACTCE, '3905531200' AS GEOID, NAME, NAMELSAD, MTFCC, FUNCSTAT, "
    "ALAND, AWATER, INTPTLAT, INTPTLON FROM tl_2020_39_tract WHERE GEOID = '39055312000'"
)

# (output folder, source file without .zip, extra ogr2ogr arguments)
ENTRIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "tiger2020",
        "tl_2020_us_state",
        ("-where", "GEOID IN ('39','54')", "-simplify", "0.01"),
    ),
    ("tiger2020", "tl_2020_us_county", ("-where", "GEOID IN ('39055','54009')")),
    ("tiger2020", "tl_2020_39_tract", ("-where", "GEOID = '39055312000'")),
    ("tiger2020", "tl_2020_39_bg", ("-where", "GEOID LIKE '39055312000%'")),
    ("tiger2020", "tl_2020_39_tabblock20", ("-where", "GEOID20 LIKE '39055312000%'")),
    ("tiger2020", "tl_2020_39_place", ("-where", "GEOID = '3959934'")),
    ("tiger2020", "tl_2020_39_cousub", ("-where", "GEOID IN ('3905577574','3905549714')")),
    (
        "malformed/missing_namelsad",
        "tl_2020_39_tract",
        (
            "-where",
            "GEOID = '39055312000'",
            "-select",
            "STATEFP,COUNTYFP,TRACTCE,GEOID,NAME,MTFCC,FUNCSTAT,ALAND,AWATER,INTPTLAT,INTPTLON",
        ),
    ),
    ("malformed/bad_geoid", "tl_2020_39_tract", ("-sql", BAD_GEOID_SQL)),
)


def build(out: str, base: str, options: tuple[str, ...]) -> Path:
    """Cut one shapefile out of the real zip and write it as a fixture zip."""
    target = FIXTURES / out / f"{base}.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        shapefile = Path(tmp) / f"{base}.shp"
        # The arguments are fixed in this file, so the subprocess checks (S603, S607) do not apply.
        subprocess.run(  # noqa: S603
            [  # noqa: S607
                "ogr2ogr",
                "-f",
                "ESRI Shapefile",
                "-lco",
                "ENCODING=UTF-8",
                str(shapefile),
                f"/vsizip/{SOURCE_DIR}/{base}.zip/{base}.shp",
                *options,
            ],
            check=True,
        )
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for part in PARTS:
                archive.write(shapefile.with_suffix(part), f"{base}{part}")
    return target


def main() -> None:
    for out, base, options in ENTRIES:
        target = build(out, base, options)
        print(f"{target.relative_to(FIXTURES)}: {target.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
