"""Load the FCC Served/Unserved file and the Census boundary files into the database."""

from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from bdc.models import Release
from etl.errors import LoadError
from etl.files import DEFAULT_DATA_DIR
from etl.load import load_served_unserved


class Command(BaseCommand):
    help = (
        "Load the FCC Served/Unserved file and the Census boundary files from the data "
        "directory, replacing any data loaded before."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--data-dir",
            type=Path,
            default=DEFAULT_DATA_DIR,
            help=f"directory holding the source files (default: {DEFAULT_DATA_DIR})",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            result = load_served_unserved(options["data_dir"], progress=self.stdout.write)
        except LoadError as error:
            raise CommandError(str(error)) from error

        release = Release.objects.get(pk=result.release_id)
        locations = result.database.rows["served_status"]
        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded {release}: {locations:,} locations in {result.seconds:.0f} s."
            )
        )
