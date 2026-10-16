"""Known-area lookups and bounded county geometry reads."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from django.contrib.gis.db.models.functions import AsGeoJSON
from django.db.models import Func, QuerySet
from rest_framework.exceptions import NotFound

from bdc.models import Release
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
from served_unserved.models import RollupLevel, ServedStatus

if TYPE_CHECKING:
    from django_stubs_ext import WithAnnotations


AREA_MODELS: dict[str, type[Boundary]] = {
    RollupLevel.COUNTY: County,
    RollupLevel.TRACT: Tract,
    RollupLevel.BLOCK_GROUP: BlockGroup,
    RollupLevel.BLOCK: Block,
    RollupLevel.PLACE: Place,
    RollupLevel.COUNTY_SUBDIVISION: CountySubdivision,
}


def require_state(code: str) -> None:
    if not State.objects.filter(pk=code).exists():
        raise NotFound()


def require_area(level: str, code: str) -> None:
    if level == RollupLevel.H3_RES8:
        # The existing cell index leads with release. Probe each catalog entry
        # instead of scanning every status for a cell absent from the dataset.
        exists = any(
            ServedStatus.objects.filter(release_id=release_id, h3_res8=code).exists()
            for release_id in Release.objects.order_by().values_list("pk", flat=True)
        )
    else:
        model = AREA_MODELS[level]
        exists = model._default_manager.filter(pk=code).exists()
    if not exists:
        raise NotFound()


class GeometryAnnotation(TypedDict):
    geojson: str


def county_geometries(state: str) -> QuerySet[WithAnnotations[County, GeometryAnnotation]]:
    # ST_ForcePolygonCCW gives RFC 7946's exterior-CCW/interior-CW winding.
    return (
        County.objects.filter(state_id=state)
        .order_by("geoid")
        .annotate(geojson=AsGeoJSON(Func("geom", function="ST_ForcePolygonCCW"), precision=15))
    )
