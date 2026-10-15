from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from core.admin import ReadOnlyModelAdmin
from geography.models import (
    Block,
    BlockGroup,
    Boundary,
    County,
    CountySubdivision,
    Place,
    State,
    Tract,
)


class BoundaryAdmin(ReadOnlyModelAdmin):
    # A read-only geometry renders as its full WKT, megabytes for one county.
    exclude = ("geom",)
    readonly_fields = ("geometry_summary",)
    search_fields = ("^geoid", "name")

    def get_queryset(self, request: HttpRequest) -> QuerySet[Boundary]:
        return super().get_queryset(request).defer("geom")

    @admin.display(description="Geometry")
    def geometry_summary(self, obj: Boundary) -> str:
        extent = tuple(round(v, 5) for v in obj.geom.extent)
        return f"{obj.geom.num_geom} polygon(s), extent {extent}"


@admin.register(State)
class StateAdmin(BoundaryAdmin):
    list_display = ("geoid", "name", "abbreviation")


@admin.register(County)
class CountyAdmin(BoundaryAdmin):
    list_display = ("geoid", "name", "state_id")


@admin.register(Tract)
class TractAdmin(BoundaryAdmin):
    list_display = ("geoid", "name", "county_id")


@admin.register(BlockGroup)
class BlockGroupAdmin(BoundaryAdmin):
    list_display = ("geoid", "name", "tract_id")


@admin.register(Block)
class BlockAdmin(BoundaryAdmin):
    list_display = (
        "geoid",
        "name",
        "block_group_id",
        "place_id",
        "county_subdivision_id",
        "population_2020",
        "housing_units_2020",
        "urban_rural",
    )
    list_filter = ("urban_rural",)


@admin.register(Place)
class PlaceAdmin(BoundaryAdmin):
    list_display = ("geoid", "name", "state_id")


@admin.register(CountySubdivision)
class CountySubdivisionAdmin(BoundaryAdmin):
    list_display = ("geoid", "name", "county_id")
