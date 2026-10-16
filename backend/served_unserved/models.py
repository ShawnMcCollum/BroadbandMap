"""Served/Unserved status of each location in each FCC release, and rollups of it by area."""

from dataclasses import dataclass

from django.db import models
from django.db.models.expressions import Combinable
from django.db.models.functions import Left
from django.db.models.lookups import Exact


class ServedStatus(models.Model):
    """A location's 100/20 Mbps status, and its block and H3 cell, in one release."""

    release = models.ForeignKey(
        "bdc.Release",
        on_delete=models.CASCADE,
        related_name="served_statuses",
        db_index=False,
    )
    # No index of its own: a search for a location names every release, so the unique
    # (release, location_id) index finds it with one probe per release (ADR 0021).
    location_id = models.BigIntegerField(
        help_text="FCC location ID from the Broadband Serviceable Location Fabric.",
    )
    block = models.ForeignKey(
        "geography.Block",
        on_delete=models.PROTECT,
        related_name="served_statuses",
        db_index=False,
        help_text="2020 census block containing the location in this release (block_geoid).",
    )
    h3_res8 = models.CharField(
        max_length=15,
        help_text=(
            "H3 resolution-8 cell index of the location in this release, lowercase hex "
            "(h3_res8_id)."
        ),
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
        ordering = ["release", "location_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["release", "location_id"],
                name="served_unserved_unique_location_per_release",
            ),
            models.CheckConstraint(
                condition=models.Q(h3_res8__regex=r"^[0-9a-f]{15}$"),
                name="served_unserved_h3_res8_format",
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
        # Every area query filters on the release, so it leads. varchar_pattern_ops serves both
        # startswith and = on block_id (ADR 0012).
        indexes = [
            models.Index(
                fields=["release", "block"],
                opclasses=["int8_ops", "varchar_pattern_ops"],
                name="servedstatus_release_block",
            ),
            models.Index(fields=["release", "h3_res8"], name="servedstatus_release_h3"),
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
    PLACE = "place", "Place"
    COUNTY_SUBDIVISION = "county_subdivision", "County subdivision"


@dataclass(frozen=True)
class AreaKey:
    """How one rollup level names its areas, and which locations lie in each.

    ``pattern`` is the regular expression a code matches in full, and ``form`` says the same in
    words. ``group_by`` gives the code of a status's area, as an expression over ServedStatus.
    ``lookup`` is the ServedStatus lookup that selects an area's statuses by its code.
    ``covers_every_location`` says whether every location lies in an area at this level: a
    location outside every place has no place.
    """

    pattern: str
    form: str
    group_by: Combinable
    lookup: str
    covers_every_location: bool


# A census code is the area's GEOID, and an H3 code is the cell index. A status's block and cell
# are those its own release gives (ADR 0012). A location is in a county, tract or block group when
# its block GEOID starts with the code, and in a block or an H3 cell when its block GEOID or cell
# index is the code. A location is in a place or county subdivision when its block's stored place
# or county subdivision is the code (see Block.place); a location outside every place has no
# place. startswith is served by the servedstatus_release_block index, whose block_id column uses
# varchar_pattern_ops. A string range would not work: in the en_US collation,
# "39049" <= block_id < "3904:" matches nothing.
AREA_KEYS: dict[str, AreaKey] = {
    RollupLevel.COUNTY: AreaKey(
        pattern="[0-9]{5}",
        form="5 digits",
        group_by=Left("block__geoid", 5),
        lookup="block__geoid__startswith",
        covers_every_location=True,
    ),
    RollupLevel.TRACT: AreaKey(
        pattern="[0-9]{11}",
        form="11 digits",
        group_by=Left("block__geoid", 11),
        lookup="block__geoid__startswith",
        covers_every_location=True,
    ),
    RollupLevel.BLOCK_GROUP: AreaKey(
        pattern="[0-9]{12}",
        form="12 digits",
        group_by=Left("block__geoid", 12),
        lookup="block__geoid__startswith",
        covers_every_location=True,
    ),
    RollupLevel.BLOCK: AreaKey(
        pattern="[0-9]{15}",
        form="15 digits",
        group_by=models.F("block__geoid"),
        lookup="block__geoid",
        covers_every_location=True,
    ),
    RollupLevel.H3_RES8: AreaKey(
        pattern="[0-9a-f]{15}",
        form="15 lowercase hex characters",
        group_by=models.F("h3_res8"),
        lookup="h3_res8",
        covers_every_location=True,
    ),
    RollupLevel.PLACE: AreaKey(
        pattern="[0-9]{7}",
        form="7 digits",
        group_by=models.F("block__place"),
        lookup="block__place",
        covers_every_location=False,
    ),
    RollupLevel.COUNTY_SUBDIVISION: AreaKey(
        pattern="[0-9]{10}",
        form="10 digits",
        group_by=models.F("block__county_subdivision"),
        lookup="block__county_subdivision",
        covers_every_location=True,
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
    """Served/Not served counts of one state's locations in one area, in one release.

    Built from the release's statuses by every data load. Only areas with at least one
    location have a row. An H3 cell on a state line has one row per state, and its counts are
    the sum of its rows (ADR 0017).
    """

    release = models.ForeignKey(
        "bdc.Release",
        on_delete=models.CASCADE,
        related_name="rollups",
        db_index=False,
    )
    state = models.ForeignKey(
        "geography.State",
        on_delete=models.PROTECT,
        related_name="rollups",
        db_index=False,
        help_text=(
            "State whose statuses the row counts. A census area's code starts with the state's "
            "FIPS code; an H3 cell on a state line has one row per state."
        ),
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
        ordering = ["release", "level", "code", "state"]
        constraints = [
            models.UniqueConstraint(
                fields=["release", "level", "code", "state"],
                name="served_unserved_rollup_unique_area_per_state",
            ),
            code_fits_level(),
            # A census area lies in one state, whose FIPS code starts its code. An H3 cell can
            # cross a state line, so its rows name the state they count (ADR 0017).
            models.CheckConstraint(
                condition=models.Q(level=RollupLevel.H3_RES8)
                | models.Q(Exact(Left("code", 2), models.F("state"))),
                name="served_unserved_rollup_code_in_state",
            ),
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
        # A data load deletes, builds and reconciles its own state's rows, level by level. The
        # unique index leads with level and code, for reads by area, so it cannot narrow those to
        # one state, and they would read every state's rows in the release (ADR 0017).
        indexes = [
            models.Index(fields=["release", "state", "level"], name="rollup_release_state_level"),
        ]

    def __str__(self) -> str:
        return f"{self.get_level_display()} {self.code} in {self.release}"
