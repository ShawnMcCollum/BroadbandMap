from summaries import (
    CountySummaries,
    Release,
    SummaryRow,
    chart_data,
    join_counties,
    table_data,
    totals,
)


def test_weighted_rate_and_missing_is_not_zero(release: Release) -> None:
    data = CountySummaries(
        release,
        "wired",
        (
            SummaryRow("39001", 1, 1, 0),
            SummaryRow("39003", 9, 1, 8),
        ),
    )
    assert totals(data) == (10, 2, 8, 20)
    counties = join_counties(data, {"39001": "Z", "39003": "A", "39005": "Missing"})
    assert [c.code for c in counties] == ["39003", "39005", "39001"]
    assert counties[1].summary is None
    table = table_data(counties)
    assert table["Locations"] == ["9", "—", "1"]
    assert table["Served share"] == ["11.1%", "No summary observation", "100.0%"]
    assert chart_data(counties)["Served share (%)"] == [100, 11.1]


def test_empty_and_share_endpoints(release: Release) -> None:
    assert totals(CountySummaries(release, "wired", ())) == (0, 0, 0, None)
    data = CountySummaries(
        release,
        "any",
        (
            SummaryRow("39003", 1, 0, 1),
            SummaryRow("39001", 2, 0, 2),
        ),
    )
    chart = chart_data(join_counties(data, {}))
    assert chart["County"] == ["39001 (39001)", "39003 (39003)"]
    assert chart["Served share (%)"] == [0, 0]
