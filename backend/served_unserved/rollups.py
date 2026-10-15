"""Served/Not served rollups: how many of an area's locations are served, by area."""

import re

from django.db import transaction
from django.db.models import Count, Q, QuerySet

from bdc.models import Release
from served_unserved.models import AREA_KEYS, AreaKey, Rollup, ServedStatus

COUNT_FIELDS = ("locations", "any_100_20", "wired_100_20", "terrestrial_100_20")


def area_key(level: str) -> AreaKey:
    """The area key of a level that has rollups. Raises ValueError for any other level."""
    try:
        return AREA_KEYS[level]
    except KeyError:
        raise ValueError(f"no rollups at level {level!r}") from None


def build_rollups(release: Release, level: str) -> int:
    """Replace the release's rollups at one level with counts of its statuses.

    Returns how many rows were written. Only areas with at least one location get a row, and a
    location with no area at the level (outside every place) is left out. Raises ValueError for
    a level without rollups.
    """
    key = area_key(level)
    areas = (
        ServedStatus.objects.filter(release=release)
        .order_by()
        .annotate(code=key.group_by)
        # A location outside every place has no place code, and adds to no row.
        .filter(code__isnull=False)
        .values("code")
        .annotate(
            n_locations=Count("pk"),
            n_any=Count("pk", filter=Q(any_100_20=True)),
            n_wired=Count("pk", filter=Q(wired_100_20=True)),
            n_terrestrial=Count("pk", filter=Q(terrestrial_100_20=True)),
        )
    )
    with transaction.atomic():
        Rollup.objects.filter(release=release, level=level).delete()
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
    return len(created)


def statuses_in(release: Release, level: str, code: str) -> QuerySet[ServedStatus]:
    """The statuses an area's rollup row counts: those in ``release`` whose location is in the area.

    Raises ValueError for a level without rollups, or a code without the level's form.
    """
    key = area_key(level)
    if not re.fullmatch(key.pattern, code):
        raise ValueError(f"{level} code {code!r} is not {key.form}")
    return ServedStatus.objects.filter(release=release, **{key.lookup: code})
