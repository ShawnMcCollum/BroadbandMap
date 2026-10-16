"""Rebuild the Served/Not served rollups from the loaded statuses."""

from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bdc.models import Release
from bdc.release_options import add_release_options, release_from_options
from core.maintenance import vacuum_analyze
from core.write_lock import WriteLockHeld, take_write_lock
from geography.models import Block
from served_unserved.models import Rollup, RollupLevel
from served_unserved.rollups import build_rollups


class Command(BaseCommand):
    help = (
        "Rebuild the Served/Not served rollups from the loaded statuses: of the release that "
        "--as-of and --processed-on name, or of every loaded release when neither is given. "
        "Then vacuum and analyze the rollups. A data load must first have assigned every census "
        "block to its place and county subdivision. Stops at once if another data load, deletion "
        "or rollup rebuild is running."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        add_release_options(parser, required=False)

    def handle(self, *args: Any, **options: Any) -> None:
        named = release_from_options(options)
        releases = list(Release.objects.all()) if named is None else [named]
        if not releases:
            raise CommandError("no release is loaded; run load_served_unserved first")
        if Block.objects.filter(county_subdivision=None).exists():
            raise CommandError(
                "some census blocks have no county subdivision; the database was loaded "
                "before blocks were assigned, so empty it and load again"
            )
        for release in releases:
            # One transaction per release, so a failure keeps that release's previous rollups.
            try:
                with transaction.atomic():
                    take_write_lock(f"rollup rebuild of {release}")
                    # By its dates: another writer may have replaced or deleted the release
                    # since it was read (ADR 0013, decision 4).
                    current = Release.objects.filter(
                        as_of=release.as_of, processed_on=release.processed_on
                    ).first()
                    if current is None:
                        raise CommandError(f"{release} is no longer loaded")
                    count = sum(build_rollups(current, level) for level in RollupLevel)
            except WriteLockHeld as error:
                raise CommandError(str(error)) from error
            self.stdout.write(self.style.SUCCESS(f"Built {count:,} rollups for {release}."))
        vacuum_analyze((Rollup,), self.stdout.write)
