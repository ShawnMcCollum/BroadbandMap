"""Rebuild the Served/Not served rollups from the loaded statuses."""

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from bdc.models import Release
from served_unserved.rollups import build_rollups


class Command(BaseCommand):
    help = "Rebuild the Served/Not served rollups of every loaded release from its statuses."

    def handle(self, *args: Any, **options: Any) -> None:
        releases = list(Release.objects.all())
        if not releases:
            raise CommandError("no release is loaded; run load_served_unserved first")
        for release in releases:
            count = build_rollups(release)
            self.stdout.write(self.style.SUCCESS(f"Built {count:,} rollups for {release}."))
