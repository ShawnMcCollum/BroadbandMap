"""Count what a load read from the source files and what the database holds, and compare them."""

from collections import Counter
from dataclasses import dataclass, field

from django.db.models import Count
from django.db.models.functions import Left

from bdc.models import Location, Release
from etl.tiger import LEVELS
from served_unserved.models import ServedStatus


@dataclass
class Counts:
    """What a load read from the source files, or found in the database."""

    rows: Counter[str] = field(default_factory=Counter)
    flag_combinations: Counter[str] = field(default_factory=Counter)
    locations_per_county: Counter[str] = field(default_factory=Counter)

    def as_dict(self) -> dict[str, dict[str, int]]:
        """Plain, sorted dictionaries, ready to store as JSON."""
        return {
            "rows": dict(sorted(self.rows.items())),
            "flag_combinations": dict(sorted(self.flag_combinations.items())),
            "locations_per_county": dict(sorted(self.locations_per_county.items())),
        }


def database_counts(release: Release) -> Counts:
    """Count the loaded rows, with statuses limited to ``release``."""
    counts = Counts()
    for level in LEVELS:
        counts.rows[level.label] = level.model._default_manager.count()
    counts.rows["location"] = Location.objects.count()

    statuses = ServedStatus.objects.filter(release=release)
    counts.rows["served_status"] = statuses.count()
    flag_rows = (
        statuses.order_by()
        .values_list("any_100_20", "wired_100_20", "terrestrial_100_20")
        .annotate(n=Count("id"))
    )
    for any_100_20, wired_100_20, terrestrial_100_20, n in flag_rows:
        counts.flag_combinations[f"{any_100_20:d},{wired_100_20:d},{terrestrial_100_20:d}"] = n

    county_rows = (
        Location.objects.order_by()
        .annotate(county=Left("block_id", 5))
        .values_list("county")
        .annotate(n=Count("location_id"))
    )
    for county, n in county_rows:
        counts.locations_per_county[county] = n
    return counts


def differences(source: Counts, database: Counts) -> list[str]:
    """Describe every count that differs between the source files and the database."""
    sections = (
        ("rows", source.rows, database.rows),
        ("flag_combinations", source.flag_combinations, database.flag_combinations),
        ("locations_per_county", source.locations_per_county, database.locations_per_county),
    )
    problems = []
    for name, from_source, from_database in sections:
        for key in sorted(from_source.keys() | from_database.keys()):
            if from_source[key] != from_database[key]:
                problems.append(
                    f"{name}[{key}]: source {from_source[key]}, database {from_database[key]}"
                )
    return problems
