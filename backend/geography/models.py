"""Census TIGER/Line 2020 boundaries, stored in WGS84."""

from django.contrib.gis.db import models
from django.db.models.functions import Left
from django.db.models.lookups import Exact


def geoid_format(length: int, model_name: str) -> models.CheckConstraint:
    """GEOIDs are fixed-length strings of digits."""
    return models.CheckConstraint(
        condition=models.Q(geoid__regex=rf"^[0-9]{{{length}}}$"),
        name=f"geography_{model_name}_geoid_format",
    )


# A boundary's parent area is named by the first digits of its own GEOID, so reading an area's
# children is a GEOID prefix read, served by the GEOID's varchar_pattern_ops index. The parent
# links have no index of their own (db_index=False). No foreign key here has a
# varchar_pattern_ops index either, since nothing compares one with LIKE (ADR 0021).


class Boundary(models.Model):
    """Fields shared by every boundary level. Each level declares its own GEOID."""

    name = models.CharField(
        max_length=100,
        help_text=(
            'Census label, e.g. "Franklin County" (NAMELSAD; NAME for states, NAME20 for blocks).'
        ),
    )
    land_area_m2 = models.BigIntegerField(help_text="Land area in square metres (ALAND).")
    water_area_m2 = models.BigIntegerField(help_text="Water area in square metres (AWATER).")
    internal_point = models.PointField(
        srid=4326,
        help_text="Census internal point (INTPTLAT/INTPTLON), used to place labels.",
    )
    geom = models.MultiPolygonField(srid=4326)

    class Meta:
        abstract = True
        ordering = ["geoid"]

    def __str__(self) -> str:
        return f"{self.name} ({self.pk})"


class State(Boundary):
    geoid = models.CharField(primary_key=True, max_length=2)
    abbreviation = models.CharField(max_length=2)

    class Meta(Boundary.Meta):
        constraints = [
            geoid_format(2, "state"),
            # A constraint, not unique=True, which would add a varchar_pattern_ops index that
            # nothing reads (ADR 0021).
            models.UniqueConstraint(
                fields=["abbreviation"], name="geography_state_unique_abbreviation"
            ),
        ]
        verbose_name = "state"
        verbose_name_plural = "states"


class County(Boundary):
    geoid = models.CharField(primary_key=True, max_length=5)
    state = models.ForeignKey(
        State, on_delete=models.PROTECT, related_name="counties", db_index=False
    )

    class Meta(Boundary.Meta):
        constraints = [geoid_format(5, "county")]
        verbose_name = "county"
        verbose_name_plural = "counties"


class Tract(Boundary):
    geoid = models.CharField(primary_key=True, max_length=11)
    county = models.ForeignKey(
        County, on_delete=models.PROTECT, related_name="tracts", db_index=False
    )

    class Meta(Boundary.Meta):
        constraints = [geoid_format(11, "tract")]
        verbose_name = "census tract"
        verbose_name_plural = "census tracts"


class BlockGroup(Boundary):
    geoid = models.CharField(primary_key=True, max_length=12)
    tract = models.ForeignKey(
        Tract, on_delete=models.PROTECT, related_name="block_groups", db_index=False
    )

    class Meta(Boundary.Meta):
        constraints = [geoid_format(12, "blockgroup")]
        verbose_name = "block group"
        verbose_name_plural = "block groups"


class Block(Boundary):
    class UrbanRural(models.TextChoices):
        URBAN = "U", "Urban"
        RURAL = "R", "Rural"

    geoid = models.CharField(primary_key=True, max_length=15)
    block_group = models.ForeignKey(
        BlockGroup, on_delete=models.PROTECT, related_name="blocks", db_index=False
    )
    population_2020 = models.PositiveIntegerField(help_text="2020 census population (POP20).")
    housing_units_2020 = models.PositiveIntegerField(
        help_text="2020 census housing units (HOUSING20)."
    )
    urban_rural = models.CharField(
        max_length=1,
        choices=UrbanRural.choices,
        help_text="2020 urban/rural classification (UR20).",
    )
    place = models.ForeignKey(
        "Place",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="blocks",
        db_index=False,
        help_text="Place that holds the block's internal point, if any. Set by every data load.",
    )
    county_subdivision = models.ForeignKey(
        "CountySubdivision",
        on_delete=models.PROTECT,
        null=True,
        related_name="blocks",
        db_index=False,
        help_text=(
            "County subdivision that holds the block's internal point. Set by every data load."
        ),
    )

    class Meta(Boundary.Meta):
        constraints = [
            geoid_format(15, "block"),
            # County subdivisions nest within counties, so a block's subdivision GEOID starts
            # with its county's GEOID.
            models.CheckConstraint(
                condition=models.Q(county_subdivision=None)
                | models.Q(Exact(Left("county_subdivision", 5), Left("geoid", 5))),
                name="geography_block_county_subdivision_in_county",
            ),
        ]
        # statuses_in selects a place's or county subdivision's blocks through these, and the
        # loader looks for blocks without a county subdivision (ADR 0021).
        indexes = [
            models.Index(fields=["place"], name="block_place"),
            models.Index(fields=["county_subdivision"], name="block_county_subdivision"),
        ]
        verbose_name = "census block"
        verbose_name_plural = "census blocks"


class Place(Boundary):
    """A city, village or other census place.

    A census block is in the place that holds its internal point (Block.place). A place's GEOID
    is not a prefix of its blocks' GEOIDs.
    """

    geoid = models.CharField(primary_key=True, max_length=7)
    state = models.ForeignKey(
        State, on_delete=models.PROTECT, related_name="places", db_index=False
    )

    class Meta(Boundary.Meta):
        constraints = [geoid_format(7, "place")]
        verbose_name = "place"
        verbose_name_plural = "places"


class CountySubdivision(Boundary):
    """A township or other county subdivision.

    A census block is in the county subdivision that holds its internal point
    (Block.county_subdivision). Its GEOID is not a prefix of its blocks' GEOIDs.
    """

    geoid = models.CharField(primary_key=True, max_length=10)
    county = models.ForeignKey(
        County, on_delete=models.PROTECT, related_name="county_subdivisions", db_index=False
    )

    class Meta(Boundary.Meta):
        constraints = [geoid_format(10, "countysubdivision")]
        verbose_name = "county subdivision"
        verbose_name_plural = "county subdivisions"
