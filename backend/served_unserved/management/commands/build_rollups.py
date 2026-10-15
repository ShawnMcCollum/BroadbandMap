"""Rebuild the Served/Not served rollups from the loaded statuses."""

from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bdc.models import Release
from geography.models import Block
from served_unserved.models import RollupLevel
from served_unserved.rollups import build_rollups


class Command(BaseCommand):
    help = (
        "Rebuild the Served/Not served rollups of every loaded release from its statuses. "
        "A data load must first have assigned every census block to its place and county "
        "subdivision."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        releases = list(Release.objects.all())
        if not releases:
            raise CommandError("no release is loaded; run load_served_unserved first")
        if Block.objects.filter(county_subdivision=None).exists():
            raise CommandError(
                "some census blocks have no county subdivision; "
                "run load_served_unserved to assign them"
            )
        for release in releases:
            # One transaction per release, so a failure keeps that release's previous rollups.
            with transaction.atomic():
                count = sum(build_rollups(release, level) for level in RollupLevel)
            self.stdout.write(self.style.SUCCESS(f"Built {count:,} rollups for {release}."))
