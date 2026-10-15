"""Served/Unserved status of each location in each FCC release, and rollups of it by area."""

from dataclasses import dataclass

from django.db import models
from django.db.models.expressions import Combinable
from django.db.models.functions import Left


class ServedStatus(models.Model):
    """A location's 100/20 Mbps status in one release."""

    release = models.ForeignKey(
        "bdc.Release",
        on_delete=models.CASCADE,
        related_name="served_statuses",
        db_index=False,
    )
    location = models.ForeignKey(
        "bdc.Location", on_delete=models.PROTECT, related_name="served_statuses"
    )
    any_100_20 = models.BooleanField(
        help_text="100/20 Mbps available by any technology, including satellite."
    )
    wired_100_20 = models.BooleanField(
        help_text="100/20 Mbps available by wired technology (fiber, cable, copper)."
    )
    terrestrial_100_20 = models.BooleanField(
        help_text="100/20 Mbps available by wired or fixed wireless technology."
    )

    class Meta:
        verbose_name = "served status"
        verbose_name_plural = "served statuses"
        ordering = ["release", "location"]
        constraints = [
            models.UniqueConstraint(
                fields=["release", "location"], name="served_unserved_unique_location_per_release"
            ),
            models.CheckConstraint(
                condition=models.Q(wired_100_20=False) | models.Q(terrestrial_100_20=True),
                name="served_unserved_wired_implies_terrestrial",
            ),
            models.CheckConstraint(
                condition=models.Q(terrestrial_100_20=False) | models.Q(any_100_20=True),
                name="served_unserved_terrestrial_implies_any",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.location_id} in {self.release}"


class RollupLevel(models.TextChoices):
    """Geographic levels that have rollups."""

    COUNTY = "county", "County"
    TRACT = "tract", "Census tract"
    BLOCK_GROUP = "block_group", "Block group"
    BLOCK = "block", "Census block"
    H3_RES8 = "h3_res8", "H3 resolution-8 cell"


@dataclass(frozen=True)
class AreaKey:
    """How one rollup level names its areas, and which locations lie in each.

    ``pattern`` is the regular expression a code matches in full, and ``form`` says the same in
    words. ``group_by`` gives the code of a status's area, as an expression over ServedStatus.
    ``lookup`` is the ServedStatus lookup that selects an area's statuses by its code.
    """

    pattern: str
    form: str
    group_by: Combinable
    lookup: str


# A census code is the area's GEOID, and an H3 code is the cell index. A location is in a
# county, tract or block group when its block GEOID starts with the code, and in a block or an
# H3 cell when its block GEOID or cell index is the code. startswith is served by the
# varchar_pattern_ops index on block_id. A string range would not work: in the en_US
# collation, "39049" <= block_id < "3904:" matches nothing.
AREA_KEYS: dict[str, AreaKey] = {
    RollupLevel.COUNTY: AreaKey(
        pattern="[0-9]{5}",
        form="5 digits",
        group_by=Left("location__block__geoid", 5),
        lookup="location__block__geoid__startswith",
    ),
    RollupLevel.TRACT: AreaKey(
        pattern="[0-9]{11}",
        form="11 digits",
        group_by=Left("location__block__geoid", 11),
        lookup="location__block__geoid__startswith",
    ),
    RollupLevel.BLOCK_GROUP: AreaKey(
        pattern="[0-9]{12}",
        form="12 digits",
        group_by=Left("location__block__geoid", 12),
        lookup="location__block__geoid__startswith",
    ),
    RollupLevel.BLOCK: AreaKey(
        pattern="[0-9]{15}",
        form="15 digits",
        group_by=models.F("location__block__geoid"),
        lookup="location__block__geoid",
    ),
    RollupLevel.H3_RES8: AreaKey(
        pattern="[0-9a-f]{15}",
        form="15 lowercase hex characters",
        group_by=models.F("location__h3_res8"),
        lookup="location__h3_res8",
    ),
}


def code_fits_level() -> models.CheckConstraint:
    """The level has rollups, and the code has that level's form."""
    condition = models.Q()
    for level, key in AREA_KEYS.items():
        condition |= models.Q(level=level, code__regex=f"^{key.pattern}$")
    return models.CheckConstraint(
        condition=condition, name="served_unserved_rollup_code_fits_level"
    )


class Rollup(models.Model):
    """Served/Not served counts for one area in one release.

    Built from the release's statuses by every data load. Only areas with at least one
    location have a row.
    """

    release = models.ForeignKey(
        "bdc.Release",
        on_delete=models.CASCADE,
        related_name="rollups",
        db_index=False,
    )
    level = models.CharField(
        max_length=20,
        choices=RollupLevel.choices,
        help_text="Geographic level of the area.",
    )
    code = models.CharField(
        max_length=15,
        help_text=(
            'Code of the area: its GEOID at a census level, e.g. "39049" for Franklin County, '
            "or its cell index at the H3 level."
        ),
    )
    locations = models.PositiveIntegerField(
        help_text="Locations in the area with a status in this release."
    )
    any_100_20 = models.PositiveIntegerField(
        help_text="Locations with 100/20 Mbps available by any technology, including satellite."
    )
    wired_100_20 = models.PositiveIntegerField(
        help_text="Locations with 100/20 Mbps available by wired technology (fiber, cable, copper)."
    )
    terrestrial_100_20 = models.PositiveIntegerField(
        help_text="Locations with 100/20 Mbps available by wired or fixed wireless technology."
    )

    class Meta:
        verbose_name = "rollup"
        verbose_name_plural = "rollups"
        ordering = ["release", "level", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["release", "level", "code"],
                name="served_unserved_rollup_unique_area_per_release",
            ),
            code_fits_level(),
            models.CheckConstraint(
                condition=models.Q(locations__gte=1),
                name="served_unserved_rollup_has_locations",
            ),
            models.CheckConstraint(
                condition=models.Q(any_100_20__lte=models.F("locations")),
                name="served_unserved_rollup_any_within_locations",
            ),
            models.CheckConstraint(
                condition=models.Q(terrestrial_100_20__lte=models.F("any_100_20")),
                name="served_unserved_rollup_terrestrial_within_any",
            ),
            models.CheckConstraint(
                condition=models.Q(wired_100_20__lte=models.F("terrestrial_100_20")),
                name="served_unserved_rollup_wired_within_terrestrial",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_level_display()} {self.code} in {self.release}"
