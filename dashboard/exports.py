"""Bounded summary CSV, including documented spreadsheet text prefixes."""

import csv
import io
from decimal import Decimal

from summaries import FCC_SOURCE, CountySummaries, join_counties

COLUMNS = (
    "county_geoid",
    "county_name",
    "locations",
    "served",
    "not_served",
    "served_share_percent",
    "flag",
    "as_of",
    "processed_on",
    "loaded_state_codes",
    "fcc_source",
    "boundary_vintage",
)


def spreadsheet_text(value: str, *, identifier: bool = False) -> str:
    if (
        identifier
        or value.startswith(("\t", "\r", "\n"))
        or value.lstrip().startswith(("=", "+", "-", "@"))
    ):
        return "'" + value
    return value


def summary_csv(data: CountySummaries, names: dict[str, str]) -> tuple[str, bytes]:
    """Serialize a completed collection. The caller must also finish the names read."""
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(COLUMNS)
    release = data.release
    states = ";".join(sorted(state.code for state in release.states))
    for county in join_counties(data, names):
        row = county.summary
        if row is None:
            continue
        share = (Decimal(row.served) * 100 / Decimal(row.locations)).quantize(Decimal("0.000001"))
        writer.writerow(
            (
                spreadsheet_text(county.code, identifier=True),
                spreadsheet_text(county.name),
                row.locations,
                row.served,
                row.not_served,
                format(share, "f").rstrip("0").rstrip("."),
                data.flag,
                release.as_of,
                release.processed_on,
                spreadsheet_text(states, identifier=True),
                FCC_SOURCE,
                data.boundary_vintage,
            )
        )
    filename = (
        f"ohio-county-summary-{release.as_of}-processed-{release.processed_on}-{data.flag}.csv"
    )
    return filename, output.getvalue().encode("utf-8-sig")
