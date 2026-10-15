"""Served/Not served rollups: how many of an area's locations are served, by area."""

import re

from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.db.models.functions import Left

from bdc.models import Release
from served_unserved.models import GEOID_LENGTHS, Rollup, ServedStatus

COUNT_FIELDS = ("locations", "any_100_20", "wired_100_20", "terrestrial_100_20")


def build_rollups(release: Release) -> int:
    """Replace the release's rollups with counts of its statuses; return how many rows were written.

    Only areas with at least one location get a row.
    """
    statuses = ServedStatus.objects.filter(release=release).order_by()
    written = 0
    with transaction.atomic():
        Rollup.objects.filter(release=release).delete()
        for level, length in GEOID_LENGTHS.items():
            areas = (
                statuses.annotate(code=Left("location__block_id", length))
                .values("code")
                .annotate(
                    n_locations=Count("pk"),
                    n_any=Count("pk", filter=Q(any_100_20=True)),
                    n_wired=Count("pk", filter=Q(wired_100_20=True)),
                    n_terrestrial=Count("pk", filter=Q(terrestrial_100_20=True)),
                )
            )
            created = Rollup.objects.bulk_create(
                (
                    Rollup(
                        release=release,
                        level=level,
                        code=area["code"],
                        locations=area["n_locations"],
                        any_100_20=area["n_any"],
                        wired_100_20=area["n_wired"],
                        terrestrial_100_20=area["n_terrestrial"],
                    )
                    for area in areas
                ),
                batch_size=1000,
            )
            written += len(created)
    return written


def statuses_in(release: Release, level: str, code: str) -> QuerySet[ServedStatus]:
    """The statuses an area's rollup row counts: those in ``release`` whose location is in the area.

    A location is in the area when its block GEOID starts with the area's code. Raises ValueError
    for a level without rollups, or a code that is not a GEOID of the level's length.
    """
    length = GEOID_LENGTHS.get(level)
    if length is None:
        raise ValueError(f"no rollups at level {level!r}")
    if not re.fullmatch(rf"[0-9]{{{length}}}", code):
        raise ValueError(f"{level} code {code!r} is not {length} digits")
    # A prefix match uses the varchar_pattern_ops index on block_id. A string range would not
    # work: in the en_US collation, "39049" <= block_id < "3904:" matches nothing.
    return ServedStatus.objects.filter(release=release, location__block__geoid__startswith=code)
