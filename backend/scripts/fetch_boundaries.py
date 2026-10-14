"""Download the Census TIGER/Line 2020 boundary files the map uses.

The sources are recorded in docs/decisions/0005-census-tiger-2020-boundaries.md.
Run it from the repository root:

    docker compose run --rm --no-deps backend python scripts/fetch_boundaries.py

Files already downloaded are skipped, so the script is safe to rerun.
"""

import argparse
import shutil
import sys
import zipfile
from pathlib import Path
from urllib.request import urlopen

BASE_URL = "https://www2.census.gov/geo/tiger/TIGER2020"
OHIO_FIPS = "39"

# State and county are published only as nationwide files.
FILES = (
    "STATE/tl_2020_us_state.zip",
    "COUNTY/tl_2020_us_county.zip",
    f"TRACT/tl_2020_{OHIO_FIPS}_tract.zip",
    f"BG/tl_2020_{OHIO_FIPS}_bg.zip",
    f"TABBLOCK20/tl_2020_{OHIO_FIPS}_tabblock20.zip",
    f"PLACE/tl_2020_{OHIO_FIPS}_place.zip",
    f"COUSUB/tl_2020_{OHIO_FIPS}_cousub.zip",
)
# Published only as one nationwide file of about 528 MB, so it is opt-in.
ZCTA_FILE = "ZCTA520/tl_2020_us_zcta520.zip"

DEFAULT_DEST = Path("/data/raw/tiger2020")
TIMEOUT_SECONDS = 60
CHUNK_BYTES = 1 << 20


class FetchError(Exception):
    """A file could not be downloaded intact."""


def fetch(url: str, dest_dir: Path) -> bool:
    """Download ``url`` into ``dest_dir``.

    Returns False when a copy of the same size is already there. The download
    is written to a ``.part`` file and renamed only once it is complete and
    the zip opens cleanly, so an interrupted run never leaves a file that looks
    finished.
    """
    target = dest_dir / url.rsplit("/", 1)[1]
    part = target.with_name(target.name + ".part")

    # Fixed https URLs only, so the scheme check (S310) does not apply.
    with urlopen(url, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        length = response.headers.get("Content-Length")
        if length is None:
            raise FetchError(f"{url}: server did not report a file size")
        expected = int(length)
        if target.exists() and target.stat().st_size == expected:
            return False

        print(f"Downloading {target.name} ({expected / 1e6:.0f} MB)...", flush=True)
        with part.open("wb") as out:
            shutil.copyfileobj(response, out, CHUNK_BYTES)

    try:
        received = part.stat().st_size
        if received != expected:
            raise FetchError(f"{url}: received {received} bytes, expected {expected}")
        try:
            with zipfile.ZipFile(part) as archive:
                bad_member = archive.testzip()
        except zipfile.BadZipFile as error:
            raise FetchError(f"{url}: not a valid zip file") from error
        if bad_member is not None:
            raise FetchError(f"{url}: corrupt member {bad_member}")
    except FetchError:
        part.unlink()
        raise

    part.replace(target)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download the Census TIGER/Line 2020 boundary files."
    )
    parser.add_argument(
        "--include-zcta",
        action="store_true",
        help="also download the nationwide ZIP Code Tabulation Area file (about 528 MB)",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=DEFAULT_DEST,
        help=f"directory to download into (default: {DEFAULT_DEST})",
    )
    args = parser.parse_args(argv)

    files = [*FILES, ZCTA_FILE] if args.include_zcta else list(FILES)
    args.dest.mkdir(parents=True, exist_ok=True)

    failures = 0
    for name in files:
        url = f"{BASE_URL}/{name}"
        try:
            if not fetch(url, args.dest):
                print(f"Already downloaded: {Path(name).name}")
        except (FetchError, OSError) as error:
            print(f"Failed: {error}", file=sys.stderr)
            failures += 1

    if failures:
        print(f"{failures} file(s) failed. Run the script again to retry.", file=sys.stderr)
        return 1
    print(f"All boundary files are in {args.dest}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
