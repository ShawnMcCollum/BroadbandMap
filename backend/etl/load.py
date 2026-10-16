"""Add one FCC release to the database, with its state's census boundaries if not yet loaded."""

import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from django.db import IntegrityError, connection, models, transaction

from bdc.models import Release
from core.write_lock import take_write_lock
from etl.assign import assign_blocks
from etl.bulk import copy_rows
from etl.errors import LoadError, ReconciliationError
from etl.fcc import LocationRow, read_locations
from etl.files import check_files, find_fcc_file, read_fcc_name, tiger_path
from etl.reconcile import Counts, database_counts, differences, expected_rollup_totals
from etl.tiger import LEVELS, read_level
from geography.models import Block, State
from served_unserved.models import Rollup, RollupLevel, ServedStatus
from served_unserved.rollups import build_rollups

# The tables data loads write. Only these tables may refer to them, so deleting a release never
# reaches other data (test_only_loader_tables_refer_to_loader_tables).
LOADER_MODELS: tuple[type[models.Model], ...] = (
    Rollup,
    ServedStatus,
    Release,
    *(level.model for level in reversed(LEVELS)),
)


def _quiet(message: str) -> None:
    """Report nothing."""


@dataclass(frozen=True)
class LoadResult:
    """What a data load wrote. The release is named by its dates, never by its id (ADR 0013)."""

    as_of: date
    processed_on: date
    source: Counts
    database: Counts
    seconds: float

    def as_dict(self) -> dict[str, object]:
        """The release's dates as ISO strings, seconds (rounded to 0.1), and both counts."""
        return {
            "as_of": self.as_of.isoformat(),
            "processed_on": self.processed_on.isoformat(),
            "seconds": round(self.seconds, 1),
            "source": self.source.as_dict(),
            "database": self.database.as_dict(),
        }


def check_one_state(state_fips: str) -> None:
    """Raise LoadError if the database holds another state's boundaries (ADR 0013)."""
    other = State.objects.exclude(pk=state_fips).values_list("name", flat=True).first()
    if other is not None:
        raise LoadError(
            f"the database holds the census boundaries of {other}; "
            f"another state ({state_fips}) cannot be loaded beside it"
        )


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


def loaded_blocks(state_fips: str) -> set[str]:
    """The GEOIDs of the state's loaded census blocks.

    Raises LoadError if a block has no county subdivision. Only a database loaded before blocks
    were assigned (ADR 0010) holds one, and its boundaries must be loaded again.
    """
    blocks = Block.objects.filter(geoid__startswith=state_fips).order_by()
    unassigned = blocks.filter(county_subdivision=None).order_by("geoid")
    geoids = list(unassigned.values_list("geoid", flat=True)[:5])
    if geoids:
        raise LoadError(
            f"census blocks without a county subdivision: {', '.join(geoids)}; "
            "the database was loaded before blocks were assigned, so empty it and load again"
        )
    return set(blocks.values_list("geoid", flat=True))


def analyze_tables(*tables: type[models.Model]) -> None:
    """Refresh the planner's statistics on tables just written, so queries on them plan well.

    Until a table is analyzed, PostgreSQL plans with the statistics it had before the load: an
    empty table, or no rows of the new release. It then plans aggregates over millions of rows
    as nested loops with on-disk sorts.
    """
    quote = connection.ops.quote_name
    names = ", ".join(quote(model._meta.db_table) for model in tables)
    with connection.cursor() as cursor:
        cursor.execute(f"ANALYZE {names}")


def tally(rows: Iterable[LocationRow], counts: Counts) -> Iterator[LocationRow]:
    """Pass the rows through, counting each one as it goes by."""
    for row in rows:
        county = row.block_geoid[:5]
        counts.flag_combinations[row.flags] += 1
        counts.locations_per_county[county] += 1
        counts.county_rollups[f"{county}:locations"] += 1
        counts.county_rollups[f"{county}:any_100_20"] += row.any_100_20
        counts.county_rollups[f"{county}:wired_100_20"] += row.wired_100_20
        counts.county_rollups[f"{county}:terrestrial_100_20"] += row.terrestrial_100_20
        yield row


def report_rows(
    progress: Callable[[str], None], model: type[models.Model], count: int, since: float
) -> None:
    """Report how many rows were written to the model's table, and how long it took."""
    progress(
        f"{model._meta.verbose_name_plural}: {count:,} rows in {time.monotonic() - since:.0f} s"
    )


def load_boundaries(
    state_fips: str,
    tiger: Mapping[str, Path],
    source: Counts,
    progress: Callable[[str], None],
) -> set[str]:
    """Load the state's census boundaries and return its block GEOIDs.

    Each block is then assigned to the place and county subdivision that hold its internal point.
    """
    geoids: dict[str, set[str]] = {}
    for level in LEVELS:
        began = time.monotonic()
        geoids[level.label] = set()
        rows = read_level(
            level,
            tiger[level.label],
            state_fips,
            geoids.get(level.parent_level) if level.parent_level else None,
            geoids[level.label],
        )
        count = copy_rows(
            level.model,
            level.columns,
            (tuple(row[column] for column in level.columns) for row in rows),
        )
        source.rows[level.label] = count
        report_rows(progress, level.model, count, began)

    check_geometries()

    began = time.monotonic()
    in_place = assign_blocks()
    progress(
        f"block assignment: {in_place:,} of {source.rows['block']:,} blocks in a place, "
        f"in {time.monotonic() - began:.0f} s"
    )
    return geoids["block"]


def load_served_unserved(
    data_dir: Path,
    progress: Callable[[str], None] = _quiet,
    *,
    fcc_file: Path | None = None,
    replace: bool = False,
) -> LoadResult:
    """Add the FCC release in ``data_dir`` to the database, beside any release already loaded.

    ``fcc_file`` names the FCC zip when ``data_dir`` holds several; a relative path is taken
    from ``data_dir``. The first load for a state also loads its census boundaries from
    ``data_dir``; later loads use the boundaries already loaded. A release that is already loaded
    is replaced when ``replace`` is set, and refused otherwise. Other releases are never changed.

    Everything happens in one transaction: if any check fails, the database is left as it was.
    The load takes no lock that holds up readers (ADR 0013). It first takes the write lock, and
    raises WriteLockHeld at once if another writer holds it (ADR 0015).
    """
    started = time.monotonic()
    fcc = find_fcc_file(data_dir) if fcc_file is None else read_fcc_name(data_dir / fcc_file)
    release = Release(
        filing_period=fcc.filing_period, as_of=fcc.as_of, processed_on=fcc.processed_on
    )
    source = Counts()
    with transaction.atomic(durable=True):
        # Before the database is read, so that nothing read here changes until the commit.
        take_write_lock(f"load of {release}")
        check_one_state(fcc.state_fips)
        loaded = Release.objects.filter(as_of=fcc.as_of, processed_on=fcc.processed_on).first()
        if loaded is not None and not replace:
            raise LoadError(f"{loaded} is already loaded; use --replace to load it again")
        state_name = State.objects.filter(pk=fcc.state_fips).values_list("name", flat=True).first()
        tiger = {
            level.label: tiger_path(data_dir, level.file_name(fcc.state_fips)) for level in LEVELS
        }
        progress(f"Checking source files in {data_dir}")
        check_files(fcc, tiger.values() if state_name is None else ())

        if loaded is not None:
            began = time.monotonic()
            Release.objects.filter(pk=loaded.pk).delete()
            progress(f"Deleted {loaded} in {time.monotonic() - began:.0f} s")

        if state_name is None:
            block_geoids = load_boundaries(fcc.state_fips, tiger, source, progress)
        else:
            progress(f"Census boundaries for {state_name} are already loaded")
            block_geoids = loaded_blocks(fcc.state_fips)

        release.save(force_insert=True)

        began = time.monotonic()
        count = copy_rows(
            ServedStatus,
            (
                "release_id",
                "location_id",
                "block_id",
                "h3_res8",
                "any_100_20",
                "wired_100_20",
                "terrestrial_100_20",
            ),
            (
                (
                    release.pk,
                    row.location_id,
                    row.block_geoid,
                    row.h3_res8,
                    row.any_100_20,
                    row.wired_100_20,
                    row.terrestrial_100_20,
                )
                for row in tally(read_locations(fcc, block_geoids, tiger["block"].name), source)
            ),
        )
        source.rows["served_status"] = count
        report_rows(progress, ServedStatus, count, began)

        if state_name is None:
            progress("Analyzing blocks and statuses")
            analyze_tables(Block, ServedStatus)
        else:
            progress("Analyzing statuses")
            analyze_tables(ServedStatus)

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
        database = database_counts(
            release, boundaries_of=fcc.state_fips if state_name is None else None
        )
        problems = differences(source, database)
        if problems:
            raise ReconciliationError(
                "database does not match the source files: " + "; ".join(problems)
            )

    return LoadResult(
        release.as_of, release.processed_on, source, database, time.monotonic() - started
    )
