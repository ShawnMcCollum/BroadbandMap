"""Bounded RFC 7946 county output."""

from itertools import pairwise

import pytest
from django.contrib.gis.geos import MultiPolygon, Polygon
from rest_framework.test import APIClient

from geography.api import views
from geography.models import County, State
from geography.tests.helpers import boundary_fields

pytestmark = pytest.mark.django_db(transaction=True)
URL = "/api/v1/geographies/county/"


def test_county_geojson_geometry_precision_orientation_and_metadata(county: County) -> None:
    county.geom = MultiPolygon(Polygon.from_bbox((-83.123456789012, 40.0, -83.1, 40.1)), srid=4326)
    county.save()
    response = APIClient().get(URL, {"state": "39"})
    assert response.status_code == 200
    assert response["Content-Type"] == "application/geo+json"
    assert response["Cache-Control"] == "no-store"
    data = response.json()
    assert set(data) == {
        "type",
        "features",
        "count",
        "next",
        "previous",
        "state",
        "boundary_vintage",
    }
    assert data["type"] == "FeatureCollection"
    assert data["boundary_vintage"] == 2020
    assert data["count"] == 1
    feature = data["features"][0]
    assert feature["type"] == "Feature"
    assert feature["id"] == "39049"
    assert feature["properties"] == {"code": "39049", "name": "Franklin County"}
    assert feature["geometry"]["type"] == "MultiPolygon"
    ring = feature["geometry"]["coordinates"][0][0]
    assert ring[0][0] == pytest.approx(-83.123456789012, abs=1e-12)
    assert 40 <= ring[0][1] <= 40.1
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in pairwise(ring))
    assert area > 0  # Exterior ring is counterclockwise.
    assert APIClient().get(URL, {"state": "39", "page": "2"}).status_code == 404


def test_empty_known_state(state: State) -> None:
    response = APIClient().get(URL, {"state": "39"})
    assert response.status_code == 200
    assert response.json()["features"] == []


def test_geojson_sorted_paging_and_inner_ring_orientation(county: County) -> None:
    County.objects.create(
        geoid="39001", state=county.state, name="Adams County", **boundary_fields()
    )
    county.geom = MultiPolygon(
        Polygon(
            ((-83, 40), (-83, 41), (-82, 41), (-82, 40), (-83, 40)),
            ((-82.8, 40.2), (-82.2, 40.2), (-82.2, 40.8), (-82.8, 40.8), (-82.8, 40.2)),
        ),
        srid=4326,
    )
    county.save()
    client = APIClient()
    first = client.get(URL, {"state": "39", "page_size": "1"}).json()
    assert first["features"][0]["id"] == "39001"
    second = client.get(first["next"]).json()
    assert second["features"][0]["id"] == "39049"
    assert second["previous"]
    assert second["next"] is None
    hole = second["features"][0]["geometry"]["coordinates"][0][1]
    assert sum(a[0] * b[1] - b[0] * a[1] for a, b in pairwise(hole)) < 0


@pytest.mark.parametrize(
    "query",
    [
        "",
        "state=3",
        "state=",
        "state=39&state=39",
        "state=39&page_size=101",
        "state=39&page_size=0",
        "state=39&as_of=2025-12-31",
        "state=39&page=0",
    ],
)
def test_geojson_query_validation(query: str) -> None:
    response = APIClient().get(URL + "?" + query)
    assert response.status_code == 400
    assert response["Content-Type"] == "application/problem+json"


def test_unknown_state_and_accept_negotiation() -> None:
    assert APIClient().get(URL, {"state": "99"}).status_code == 404
    response = APIClient().get(URL, {"state": "39"}, HTTP_ACCEPT="application/json")
    assert response.status_code == 406
    assert response["Content-Type"] == "application/problem+json"


def test_geojson_payload_preflight_and_full_envelope_caps(
    county: County, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = APIClient()
    full_size = len(client.get(URL, {"state": "39"}).content)
    monkeypatch.setattr(views, "MAX_GEOMETRY_BYTES", full_size)
    assert client.get(URL, {"state": "39"}).status_code == 200
    monkeypatch.setattr(views, "MAX_GEOMETRY_BYTES", full_size - 1)
    response = client.get(URL, {"state": "39"})
    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "geometry_payload_too_large"
    monkeypatch.setattr(views, "MAX_GEOMETRY_BYTES", 1)
    assert client.get(URL, {"state": "39"}).status_code == 400


def test_geojson_head_options_and_write_rejection(county: County) -> None:
    client = APIClient()
    head = client.head(URL, {"state": "39"})
    assert head.status_code == 200
    assert head.content == b""
    assert client.options(URL).status_code == 200
    for method in ["post", "put", "patch", "delete"]:
        response = getattr(client, method)(URL)
        assert response.status_code == 405
        assert response["Content-Type"] == "application/problem+json"
