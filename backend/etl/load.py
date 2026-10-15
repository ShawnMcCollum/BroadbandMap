"""Replace the loaded data with the FCC release and census boundaries in a data directory."""

import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from django.db import IntegrityError, connection, models, transaction

from bdc.models import Location, Release
from etl.assign import assign_blocks
from etl.bulk import copy_rows
from etl.errors import LoadError, ReconciliationError
from etl.fcc import LocationRow, read_locations
from etl.files import check_files, find_fcc_file, tiger_path
from etl.reconcile import Counts, database_counts, differences, expected_rollup_totals
from etl.tiger import LEVELS, read_level
from geography.models import Block
from served_unserved.models import Rollup, RollupLevel, ServedStatus
from served_unserved.rollups import build_rollups

LOADER_MODELS: tuple[type[models.Model], ...] = (
    Rollup,
    ServedStatus,
    Location,
    Release,
    *(level.model for level in reversed(LEVELS)),
)


def _quiet(message: str) -> None:
    """Report nothing."""


@dataclass(frozen=True)
class LoadResult:
    release_id: int
    source: Counts
    database: Counts
    seconds: float

    def as_dict(self) -> dict[str, object]:
        """release_id, seconds (rounded to 0.1), source and database as dictionaries."""
        return {
            "release_id": self.release_id,
            "seconds": round(self.seconds, 1),
            "source": self.source.as_dict(),
            "database": self.database.as_dict(),
        }


def clear_tables() -> None:
    """Empty every table the loader owns, in one statement."""
    quote = connection.ops.quote_name
    tables = ", ".join(quote(model._meta.db_table) for model in LOADER_MODELS)
    with connection.cursor() as cursor:
        cursor.execute(f"TRUNCATE {tables}")


def check_geometries() -> None:
    """Raise LoadError if PostGIS finds an invalid geometry in any boundary table."""
    for level in LEVELS:
        invalid = level.model._default_manager.filter(geom__isvalid=False)
        geoids = [str(pk) for pk in invalid.values_list("pk", flat=True)[:5]]
        if geoids:
            raise LoadError(
                f"{level.model._meta.verbose_name_plural}: "
                f"invalid geometry for GEOID {', '.join(geoids)}"
            )


def analyze_tables(*tables: type[models.Model]) -> None:
    """Refresh the planner's statistics on tables just written, so queries on them plan well.

    After TRUNCATE, PostgreSQL treats a table as empty until it is analyzed. It then plans
    aggregates over millions of rows as nested loops with on-disk sorts.
    """
    quote = connection.ops.quote_name
    names = ", ".join(quote(model._meta.db_table) for model in tables)
    with connection.cursor() as cursor:
        cursor.execute(f"ANALYZE {names}")


def tally(rows: Iterable[LocationRow], counts: Counts) -> Iterator[LocationRow]:
    """Pass the rows through, counting each one as it goes by."""
    for row in rows:
        county = row.block_geoid[:5]
        counts.rows["location"] += 1
        counts.flag_combinations[row.flags] += 1
        counts.locations_per_county[county] += 1
        counts.county_rollups[f"{county}:locations"] += 1
        counts.county_rollups[f"{county}:any_100_20"] += row.any_100_20
        counts.county_rollups[f"{county}:wired_100_20"] += row.wired_100_20
        counts.county_rollups[f"{county}:terrestrial_100_20"] += row.terrestrial_100_20
        yield row


def load_served_unserved(data_dir: Path, progress: Callable[[str], None] = _quiet) -> LoadResult:
    """Replace the loaded data with the FCC release and census boundaries in ``data_dir``.

    Everything happens in one transaction: if any check fails, the database is left as it was.
    """
    started = time.monotonic()
    fcc = find_fcc_file(data_dir)
    tiger = {level.label: tiger_path(data_dir, level.file_name(fcc.state_fips)) for level in LEVELS}
    progress(f"Checking source files in {data_dir}")
    check_files(fcc, tiger.values())

    def written(model: type[models.Model], count: int, since: float) -> None:
        progress(
            f"{model._meta.verbose_name_plural}: {count:,} rows in {time.monotonic() - since:.0f} s"
        )

    source = Counts()
    geoids: dict[str, set[str]] = {}
    with transaction.atomic(durable=True):
        clear_tables()

        for level in LEVELS:
            began = time.monotonic()
            geoids[level.label] = set()
            rows = read_level(
                level,
                tiger[level.label],
                fcc.state_fips,
                geoids.get(level.parent_level) if level.parent_level else None,
                geoids[level.label],
            )
            count = copy_rows(
                level.model,
                level.columns,
                (tuple(row[column] for column in level.columns) for row in rows),
            )
            source.rows[level.label] = count
            written(level.model, count, began)

        check_geometries()

        began = time.monotonic()
        in_place = assign_blocks()
        progress(
            f"block assignment: {in_place:,} of {source.rows['block']:,} blocks in a place, "
            f"in {time.monotonic() - began:.0f} s"
        )

        release = Release.objects.create(
            filing_period=fcc.filing_period, as_of=fcc.as_of, processed_on=fcc.processed_on
        )

        began = time.monotonic()
        count = copy_rows(
            Location,
            ("location_id", "block_id", "h3_res8"),
            (
                (row.location_id, row.block_geoid, row.h3_res8)
                for row in tally(read_locations(fcc, geoids["block"], tiger["block"].name), source)
            ),
        )
        written(Location, count, began)

        began = time.monotonic()
        count = copy_rows(
            ServedStatus,
            (
                "release_id",
                "location_id",
                "any_100_20",
                "wired_100_20",
                "terrestrial_100_20",
            ),
            (
                (
                    release.pk,
                    row.location_id,
                    row.any_100_20,
                    row.wired_100_20,
                    row.terrestrial_100_20,
                )
                for row in read_locations(fcc, geoids["block"], tiger["block"].name)
            ),
        )
        source.rows["served_status"] = count
        written(ServedStatus, count, began)

        progress("Analyzing blocks, locations and statuses")
        analyze_tables(Block, Location, ServedStatus)

        for rollup_level in RollupLevel:
            began = time.monotonic()
            count = build_rollups(release, rollup_level)
            progress(
                f"rollups by {rollup_level}: {count:,} rows in {time.monotonic() - began:.0f} s"
            )

        progress("Checking foreign keys")
        try:
            connection.check_constraints()
        except IntegrityError as error:
            raise LoadError(f"foreign key check failed: {error}") from error

        source.rollup_totals = expected_rollup_totals(source.county_rollups)
        progress("Reconciling counts")
        database = database_counts(release)
        problems = differences(source, database)
        if problems:
            raise ReconciliationError(
                "database does not match the source files: " + "; ".join(problems)
            )

    return LoadResult(release.pk, source, database, time.monotonic() - started)
