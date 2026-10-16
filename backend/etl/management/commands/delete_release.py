"""Delete one release, with its statuses and rollups."""

import time
from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bdc.models import Release
from bdc.release_options import add_release_options, find_release
from core.maintenance import vacuum_analyze
from core.write_lock import WriteLockHeld, take_write_lock
from served_unserved.models import Rollup, ServedStatus


class Command(BaseCommand):
    help = (
        "Delete the release that --as-of and --processed-on name, with its statuses and rollups, "
        "in one transaction. Other releases are not changed. Once the deletion has committed, "
        "the statuses, rollups and releases are vacuumed and analyzed. Stops at once if another "
        "data load, deletion or rollup rebuild is running."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        add_release_options(parser, required=True)
        parser.add_argument(
            "--noinput",
            "--no-input",
            action="store_false",
            dest="interactive",
            help="delete without asking for confirmation",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        release = find_release(options["as_of"], options["processed_on"])
        if options["interactive"]:
            try:
                answer = input(
                    f"Delete {release}, with its statuses and rollups? "
                    "Type 'yes' to continue, or 'no' to cancel: "
                )
            except EOFError:
                raise CommandError(
                    "no answer to the confirmation question; "
                    "use --no-input to delete without asking"
                ) from None
            if answer != "yes":
                self.stdout.write("Deletion cancelled.")
                return

        began = time.monotonic()
        # By its dates, not its id: a replace while the question was open gives the release a
        # new id (ADR 0013, decision 4).
        try:
            with transaction.atomic(durable=True):
                # After the answer, so that no lock is held while waiting for one.
                take_write_lock(f"deletion of {release}")
                _, deleted = Release.objects.filter(
                    as_of=release.as_of, processed_on=release.processed_on
                ).delete()
        except WriteLockHeld as error:
            raise CommandError(str(error)) from error
        if not deleted.get(Release._meta.label):
            raise CommandError(f"{release} is no longer loaded")
        statuses = deleted.get(ServedStatus._meta.label, 0)
        rollups = deleted.get(Rollup._meta.label, 0)
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {release}: {statuses:,} statuses and {rollups:,} rollups "
                f"in {time.monotonic() - began:.0f} s."
            )
        )
        vacuum_analyze((ServedStatus, Rollup, Release), self.stdout.write)
