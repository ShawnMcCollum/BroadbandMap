"""Assign each census block to the place and county subdivision that hold its internal point."""

from django.db import connection

from etl.errors import LoadError
from geography.models import Block

# Blocks nest within places and county subdivisions, and a block's internal point lies inside
# the block, so the areas that hold the point are the block's areas. A county subdivision is
# matched only within the block's county.
#
# Each join loops over the areas and finds the internal points each one holds through the GiST
# index on geography_block.internal_point, so PostGIS prepares each area's polygon once. The
# ORM cannot join two unrelated tables on a spatial test: it writes one subquery per block,
# which took 63 s against 27 s. ST_Intersects rather than ST_Contains: a point on a boundary
# shared by two areas then matches both, and AMBIGUOUS_BLOCKS reports it.
#
# Each data load assigns only its own state's blocks (ADR 0017).

# Blocks whose internal point lies in two places, or in two county subdivisions of their county.
AMBIGUOUS_BLOCKS = """
SELECT b.geoid, 'places', string_agg(p.geoid, ', ' ORDER BY p.geoid)
FROM geography_place AS p
JOIN geography_block AS b ON ST_Intersects(p.geom, b.internal_point)
WHERE p.state_id = %(state)s AND b.geoid LIKE %(prefix)s
GROUP BY b.geoid
HAVING count(*) > 1
UNION ALL
SELECT b.geoid, 'county subdivisions', string_agg(c.geoid, ', ' ORDER BY c.geoid)
FROM geography_countysubdivision AS c
JOIN geography_block AS b
    ON ST_Intersects(c.geom, b.internal_point) AND c.county_id = left(b.geoid, 5)
WHERE c.county_id LIKE %(prefix)s AND b.geoid LIKE %(prefix)s
GROUP BY b.geoid
HAVING count(*) > 1
ORDER BY 1, 2
LIMIT 5
"""

# Set every block's place and county subdivision, NULL where no area holds its point.
# MATERIALIZED keeps each join in the shape above: inlined into the UPDATE, the planner probes
# the places once per block instead.
ASSIGN_BLOCKS = """
WITH in_place AS MATERIALIZED (
    SELECT b.geoid AS block_id, p.geoid AS place_id
    FROM geography_place AS p
    JOIN geography_block AS b ON ST_Intersects(p.geom, b.internal_point)
    WHERE p.state_id = %(state)s AND b.geoid LIKE %(prefix)s
),
in_county_subdivision AS MATERIALIZED (
    SELECT b.geoid AS block_id, c.geoid AS county_subdivision_id
    FROM geography_countysubdivision AS c
    JOIN geography_block AS b
        ON ST_Intersects(c.geom, b.internal_point) AND c.county_id = left(b.geoid, 5)
    WHERE c.county_id LIKE %(prefix)s AND b.geoid LIKE %(prefix)s
)
UPDATE geography_block AS g
SET place_id = p.place_id, county_subdivision_id = c.county_subdivision_id
FROM geography_block AS b
LEFT JOIN in_county_subdivision AS c ON c.block_id = b.geoid
LEFT JOIN in_place AS p ON p.block_id = b.geoid
WHERE g.geoid = b.geoid AND b.geoid LIKE %(prefix)s
"""


def assign_blocks(state_fips: str) -> int:
    """Set every block of the state to the place and county subdivision that hold its internal
    point.

    Blocks and areas of other states are not read or changed. Returns how many blocks are in a
    place. Raises LoadError if a block's internal point lies in two places, or in two county
    subdivisions of its county, or in none of them.
    """
    params = {"state": state_fips, "prefix": f"{state_fips}%"}
    with connection.cursor() as cursor:
        cursor.execute(AMBIGUOUS_BLOCKS, params)
        ambiguous = cursor.fetchall()
        if ambiguous:
            raise LoadError(
                "census blocks whose internal point lies in more than one area: "
                + ", ".join(f"{geoid} ({areas} {codes})" for geoid, areas, codes in ambiguous)
            )
        cursor.execute(ASSIGN_BLOCKS, params)
    blocks = Block.objects.filter(geoid__startswith=state_fips)
    unassigned = blocks.filter(county_subdivision=None).order_by("geoid")
    geoids = list(unassigned.values_list("geoid", flat=True)[:5])
    if geoids:
        raise LoadError(f"census blocks in no county subdivision: {', '.join(geoids)}")
    return blocks.exclude(place=None).count()
