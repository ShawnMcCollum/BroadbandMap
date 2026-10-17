import csv
import io
from dataclasses import replace

import pytest

from exports import COLUMNS, spreadsheet_text, summary_csv
from summaries import FCC_SOURCE, CountySummaries, Release, State, SummaryRow


def test_csv_context_counts_and_roundtrip(release: Release) -> None:
    release = replace(release, states=(State("01", "Alabama", "AL"), *release.states))
    data = CountySummaries(
        release,
        "wired",
        (
            SummaryRow("01001", 9, 1, 8),
            SummaryRow("39003", 1, 0, 1),
        ),
    )
    name = '  =HYPERLINK("example"),\nCounty'
    filename, payload = summary_csv(data, {"01001": name, "39005": "Missing"})
    assert payload.startswith(b"\xef\xbb\xbf")
    assert filename == "ohio-county-summary-2025-12-31-processed-2026-09-29-wired.csv"
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    records = list(reader)
    assert reader.fieldnames == list(COLUMNS)
    assert len(records) == 2
    first = next(r for r in records if r["county_geoid"] == "'01001")
    assert first == {
        "county_geoid": "'01001",
        "county_name": "'" + name,
        "locations": "9",
        "served": "1",
        "not_served": "8",
        "served_share_percent": "11.111111",
        "flag": "wired",
        "as_of": "2025-12-31",
        "processed_on": "2026-09-29",
        "loaded_state_codes": "'01;39",
        "fcc_source": FCC_SOURCE,
        "boundary_vintage": "2020",
    }
    assert next(r for r in records if r["county_geoid"] == "'39003")["served_share_percent"] == "0"


@pytest.mark.parametrize(
    "value", ["=1+1", "+1", "-1", "@SUM(1)", "  =foo", "\tfoo", "\rfoo", "\nfoo"]
)
def test_spreadsheet_safe_text(value: str) -> None:
    assert spreadsheet_text(value) == "'" + value


def test_ordinary_text_and_identifier() -> None:
    assert spreadsheet_text('County, "quoted"\nline') == 'County, "quoted"\nline'
    assert spreadsheet_text("01001", identifier=True) == "'01001"
