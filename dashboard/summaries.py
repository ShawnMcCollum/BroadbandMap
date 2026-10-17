"""API domain values and pure county analysis; no HTTP or Streamlit state."""

from dataclasses import dataclass
from typing import Literal

type Flag = Literal["wired", "any", "terrestrial"]
type ReleaseKey = tuple[str, str]

FLAGS: dict[Flag, str] = {
    "wired": "Wired",
    "any": "Any technology",
    "terrestrial": "Terrestrial",
}
FCC_SOURCE = "FCC National Broadband Map Served/Unserved"


@dataclass(frozen=True)
class State:
    code: str
    name: str
    abbreviation: str


@dataclass(frozen=True)
class Release:
    as_of: str
    processed_on: str
    filing_period: str
    states: tuple[State, ...]

    @property
    def key(self) -> ReleaseKey:
        return self.as_of, self.processed_on

    @property
    def has_ohio(self) -> bool:
        return any(state.code == "39" for state in self.states)

    @property
    def label(self) -> str:
        return f"{self.as_of} · processed {self.processed_on} · {self.filing_period}"


@dataclass(frozen=True)
class SummaryRow:
    code: str
    locations: int
    served: int
    not_served: int

    @property
    def share(self) -> float:
        return self.served / self.locations * 100


@dataclass(frozen=True)
class CountySummaries:
    """Only a successfully completed and validated API collection creates this value."""

    release: Release
    flag: Flag
    rows: tuple[SummaryRow, ...]
    boundary_vintage: int = 2020


@dataclass(frozen=True)
class CountyView:
    code: str
    name: str
    summary: SummaryRow | None


def join_counties(data: CountySummaries, names: dict[str, str]) -> list[CountyView]:
    observed = {row.code: row for row in data.rows}
    return sorted(
        (CountyView(code, names.get(code, code), observed.get(code)) for code in names | observed),
        key=lambda county: (county.name, county.code),
    )


def totals(data: CountySummaries) -> tuple[int, int, int, float | None]:
    locations = sum(row.locations for row in data.rows)
    served = sum(row.served for row in data.rows)
    return locations, served, locations - served, served / locations * 100 if locations else None


def table_data(counties: list[CountyView]) -> dict[str, list[str]]:
    return {
        "County": [county.name for county in counties],
        "County GEOID": [county.code for county in counties],
        "Locations": [f"{c.summary.locations:,}" if c.summary else "—" for c in counties],
        "Served": [f"{c.summary.served:,}" if c.summary else "—" for c in counties],
        "Not served": [f"{c.summary.not_served:,}" if c.summary else "—" for c in counties],
        "Served share": [
            f"{c.summary.share:.1f}%" if c.summary else "No summary observation" for c in counties
        ],
    }


def chart_data(counties: list[CountyView]) -> dict[str, list[str] | list[float]]:
    observed = sorted(
        (c for c in counties if c.summary is not None),
        key=lambda c: (-(c.summary.share if c.summary else 0), c.code),
    )
    return {
        "County": [f"{c.name} ({c.code})" for c in observed],
        "Served share (%)": [round(c.summary.share, 1) for c in observed if c.summary is not None],
    }
