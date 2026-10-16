"""Add a release from an FCC Served/Unserved file, with the Census boundaries on the first load."""

from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from bdc.models import Release
from core.maintenance import vacuum_analyze
from core.write_lock import WriteLockHeld
from etl.errors import LoadError
from etl.files import DEFAULT_DATA_DIR
from etl.load import LOADER_MODELS, load_served_unserved
from geography.models import State


class Command(BaseCommand):
    help = (
        "Add the state's FCC Served/Unserved file to its release, beside the states and "
        "releases already loaded. The first load of a state also loads its Census boundary files "
        "from the data directory. Once the load has committed, the loaded tables are vacuumed "
        "and analyzed. Stops at once if another data load, deletion or rollup rebuild is running."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--data-dir",
            type=Path,
            default=DEFAULT_DATA_DIR,
            help=f"directory holding the source files (default: {DEFAULT_DATA_DIR})",
        )
        parser.add_argument(
            "--fcc-file",
            type=Path,
            help=(
                "FCC Served/Unserved zip to load, when the data directory holds more than one; "
                "a relative path is taken from the data directory"
            ),
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help=(
                "load the state again if its release already holds it, replacing its statuses "
                "and rollups there"
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            result = load_served_unserved(
                options["data_dir"],
                progress=self.stdout.write,
                fcc_file=options["fcc_file"],
                replace=options["replace"],
            )
        except (LoadError, WriteLockHeld) as error:
            raise CommandError(str(error)) from error

        release = Release.objects.get(as_of=result.as_of, processed_on=result.processed_on)
        state = State.objects.only("name").get(pk=result.state_fips)
        locations = result.database.rows["served_status"]
        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded {state.name} into {release}: {locations:,} locations in "
                f"{result.seconds:.0f} s."
            )
        )
        vacuum_analyze(LOADER_MODELS, self.stdout.write)
