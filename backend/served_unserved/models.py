"""Served/Unserved status of each location in each FCC release, and rollups of it by area."""

from django.db import models


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


# Length of each level's GEOID. An area's code is its GEOID, and a location lies in the area
# when its block GEOID starts with the code.
GEOID_LENGTHS: dict[str, int] = {RollupLevel.COUNTY: 5}


def code_fits_level() -> models.CheckConstraint:
    """The level has rollups, and the code is a GEOID of that level's length."""
    condition = models.Q()
    for level, length in GEOID_LENGTHS.items():
        condition |= models.Q(level=level, code__regex=rf"^[0-9]{{{length}}}$")
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
            'GEOID of the area at its level, e.g. "39049" for Franklin County. '
            "A location is in the area when its block GEOID starts with this code."
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
