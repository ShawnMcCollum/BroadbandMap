"""Read Census TIGER/Line 2020 shapefiles into boundary rows ready for COPY."""

import functools
import re
from collections.abc import Iterator
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from pathlib import Path

from django.contrib.gis.gdal import CoordTransform, DataSource, OGRGeometry, SpatialReference
from django.contrib.gis.gdal.error import GDALException
from django.contrib.gis.gdal.feature import Feature
from django.contrib.gis.geos import MultiPolygon, Point, Polygon

from etl.errors import LoadError
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

NAD83 = 4269
WGS84 = 4326
MAX_NAME_LENGTH = 100
COORDINATE = re.compile(r"^[+-][0-9]+\.[0-9]+$")
ABBREVIATION = re.compile(r"^[A-Z]{2}$")

Row = dict[str, object]


@functools.cache
def nad83_to_wgs84() -> CoordTransform:
    return CoordTransform(SpatialReference(NAD83), SpatialReference(WGS84))


def multipolygon_hex(geom: OGRGeometry) -> str:
    """Reproject a NAD83 polygon to WGS84 and return it as a MultiPolygon in hex EWKB."""
    geom.transform(nad83_to_wgs84())
    shape = geom.geos
    if isinstance(shape, Polygon):
        shape = MultiPolygon(shape, srid=WGS84)
    return shape.hexewkb.decode()


def point_hex(lon: float, lat: float) -> str:
    """Reproject a NAD83 point to WGS84 and return it in hex EWKB."""
    point = Point(lon, lat, srid=NAD83)
    point.transform(nad83_to_wgs84())
    return point.hexewkb.decode()


@dataclass(frozen=True)
class Level:
    """One boundary file: where it comes from and how its fields map to the model."""

    label: str
    model: type[Boundary]
    file: str
    geoid_length: int
    geoid_field: str
    name_field: str
    suffix: str
    parent_column: str | None
    parent_level: str | None
    parent_fields: tuple[tuple[str, int], ...]
    nationwide: bool
    extra: tuple[tuple[str, str], ...] = ()

    def file_name(self, state_fips: str) -> str:
        return self.file.format(state=state_fips)

    @property
    def columns(self) -> tuple[str, ...]:
        parent = (self.parent_column,) if self.parent_column else ()
        extra = tuple(column for column, _ in self.extra)
        return ("geoid", "name", "land_area_m2", "water_area_m2", "internal_point", "geom") + (
            parent + extra
        )

    def required_fields(self) -> list[str]:
        fields = [
            self.geoid_field,
            self.name_field,
            f"ALAND{self.suffix}",
            f"AWATER{self.suffix}",
            f"INTPTLAT{self.suffix}",
            f"INTPTLON{self.suffix}",
            *(field for field, _ in self.parent_fields),
            *(source for _, source in self.extra),
        ]
        if self.nationwide:
            fields.append("STATEFP")
        return list(dict.fromkeys(fields))


LEVELS = (
    Level(
        label="state",
        model=State,
        file="tl_2020_us_state",
        geoid_length=2,
        geoid_field="GEOID",
        name_field="NAME",
        suffix="",
        parent_column=None,
        parent_level=None,
        parent_fields=(),
        nationwide=True,
        extra=(("abbreviation", "STUSPS"),),
    ),
    Level(
        label="county",
        model=County,
        file="tl_2020_us_county",
        geoid_length=5,
        geoid_field="GEOID",
        name_field="NAMELSAD",
        suffix="",
        parent_column="state_id",
        parent_level="state",
        parent_fields=(("STATEFP", 2),),
        nationwide=True,
    ),
    Level(
        label="tract",
        model=Tract,
        file="tl_2020_{state}_tract",
        geoid_length=11,
        geoid_field="GEOID",
        name_field="NAMELSAD",
        suffix="",
        parent_column="county_id",
        parent_level="county",
        parent_fields=(("STATEFP", 2), ("COUNTYFP", 3)),
        nationwide=False,
    ),
    Level(
        label="block_group",
        model=BlockGroup,
        file="tl_2020_{state}_bg",
        geoid_length=12,
        geoid_field="GEOID",
        name_field="NAMELSAD",
        suffix="",
        parent_column="tract_id",
        parent_level="tract",
        parent_fields=(("STATEFP", 2), ("COUNTYFP", 3), ("TRACTCE", 6)),
        nationwide=False,
    ),
    Level(
        label="block",
        model=Block,
        file="tl_2020_{state}_tabblock20",
        geoid_length=15,
        geoid_field="GEOID20",
        name_field="NAME20",
        suffix="20",
        parent_column="block_group_id",
        parent_level="block_group",
        parent_fields=(("STATEFP20", 2), ("COUNTYFP20", 3), ("TRACTCE20", 6), ("BLOCKCE20", 1)),
        nationwide=False,
        extra=(
            ("population_2020", "POP20"),
            ("housing_units_2020", "HOUSING20"),
            ("urban_rural", "UR20"),
        ),
    ),
    Level(
        label="place",
        model=Place,
        file="tl_2020_{state}_place",
        geoid_length=7,
        geoid_field="GEOID",
        name_field="NAMELSAD",
        suffix="",
        parent_column="state_id",
        parent_level="state",
        parent_fields=(("STATEFP", 2),),
        nationwide=False,
    ),
    Level(
        label="county_subdivision",
        model=CountySubdivision,
        file="tl_2020_{state}_cousub",
        geoid_length=10,
        geoid_field="GEOID",
        name_field="NAMELSAD",
        suffix="",
        parent_column="county_id",
        parent_level="county",
        parent_fields=(("STATEFP", 2), ("COUNTYFP", 3)),
        nationwide=False,
    ),
)


def read_level(
    level: Level,
    path: Path,
    state_fips: str,
    parents: AbstractSet[str] | None,
    geoids: set[str],
) -> Iterator[Row]:
    """Yield one row per feature of the level's shapefile that belongs to the state.

    Every GEOID yielded is added to ``geoids``, which the next level passes as ``parents``.
    """
    try:
        source = DataSource(f"/vsizip/{path}/{level.file_name(state_fips)}.shp")
    except GDALException as error:
        raise LoadError(f"{path.name}: cannot read the shapefile ({error})") from error
    layer = source[0]

    missing = [field for field in level.required_fields() if field not in layer.fields]
    if missing:
        raise LoadError(f"{path.name}: missing fields: {', '.join(missing)}")
    srid = layer.srs.srid if layer.srs is not None else None
    if srid != NAD83:
        raise LoadError(f"{path.name}: expected NAD83 (EPSG:{NAD83}), found {srid}")

    kept = 0
    for feature in layer:
        if level.nationwide and feature.get("STATEFP") != state_fips:
            continue
        try:
            row = feature_row(level, feature, parents, geoids)
        except ValueError as error:
            raise LoadError(f"{path.name}: feature {feature.fid}: {error}") from error
        kept += 1
        yield row
    if not kept:
        raise LoadError(f"{path.name}: no features for state {state_fips}")


def feature_row(
    level: Level, feature: Feature, parents: AbstractSet[str] | None, geoids: set[str]
) -> Row:
    """Check one feature and convert it to a row. Raise ValueError describing the first problem."""
    geoid = feature.get(level.geoid_field)
    if not (
        isinstance(geoid, str)
        and len(geoid) == level.geoid_length
        and geoid.isascii()
        and geoid.isdigit()
    ):
        raise ValueError(f"{level.geoid_field} {geoid!r} is not {level.geoid_length} digits")
    if geoid in geoids:
        raise ValueError(f"duplicate {level.geoid_field} {geoid}")

    parent = ""
    if level.parent_level is not None:
        parent = "".join(str(feature.get(field))[:size] for field, size in level.parent_fields)
        if not geoid.startswith(parent):
            raise ValueError(
                f"{level.geoid_field} {geoid} does not start with its "
                f"{level.parent_level} GEOID {parent}"
            )
        if parents is not None and parent not in parents:
            raise ValueError(f"{level.parent_level} {parent} was not loaded")

    name = feature.get(level.name_field)
    if not (isinstance(name, str) and 0 < len(name) <= MAX_NAME_LENGTH):
        raise ValueError(
            f"{level.name_field} {name!r} is empty or longer than {MAX_NAME_LENGTH} characters"
        )

    for field in (f"ALAND{level.suffix}", f"AWATER{level.suffix}"):
        value = feature.get(field)
        if not is_count(value):
            raise ValueError(f"{field} {value!r} is not a non-negative integer")

    lat = feature.get(f"INTPTLAT{level.suffix}")
    lon = feature.get(f"INTPTLON{level.suffix}")
    latitude = parse_coordinate(lat, 90)
    longitude = parse_coordinate(lon, 180)
    if latitude is None or longitude is None:
        raise ValueError(f"internal point ({lat!r}, {lon!r}) is not a valid coordinate")

    try:
        geom = feature.geom
    except GDALException as error:
        raise ValueError("has no geometry") from error
    if geom.geom_name not in ("POLYGON", "MULTIPOLYGON"):
        raise ValueError(f"geometry is {geom.geom_name}, expected a polygon")
    geom_hex = multipolygon_hex(geom)
    if geom.empty:
        raise ValueError("geometry is empty")

    extra: Row = {}
    for column, field in level.extra:
        value = feature.get(field)
        if not is_valid_extra(column, value):
            raise ValueError(f"{field} {value!r} is not valid")
        extra[column] = value

    geoids.add(geoid)
    row: Row = {
        "geoid": geoid,
        "name": name,
        "land_area_m2": feature.get(f"ALAND{level.suffix}"),
        "water_area_m2": feature.get(f"AWATER{level.suffix}"),
        "internal_point": point_hex(longitude, latitude),
        "geom": geom_hex,
    }
    if level.parent_column:
        row[level.parent_column] = parent
    return row | extra


def is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def parse_coordinate(text: object, limit: float) -> float | None:
    """The value of a coordinate such as "+41.4993217", or None if it is not valid."""
    if not isinstance(text, str) or not COORDINATE.match(text):
        return None
    value = float(text)
    return value if -limit <= value <= limit else None


def is_valid_extra(column: str, value: object) -> bool:
    """Whether ``value`` is acceptable for one of a level's extra columns."""
    if column == "abbreviation":
        return isinstance(value, str) and ABBREVIATION.match(value) is not None
    if column == "urban_rural":
        return value in ("U", "R")
    return is_count(value)
