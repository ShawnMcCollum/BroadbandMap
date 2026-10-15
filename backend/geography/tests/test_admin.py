import pytest
from django.test import Client
from django.urls import reverse

from geography.models import Block, Boundary

BOUNDARY_FIXTURES = [
    "state",
    "county",
    "tract",
    "block_group",
    "block",
    "place",
    "county_subdivision",
]


def admin_url(obj: Boundary, view: str, *args: object) -> str:
    return reverse(f"admin:{obj._meta.app_label}_{obj._meta.model_name}_{view}", args=args)


@pytest.fixture(params=BOUNDARY_FIXTURES)
def boundary(request: pytest.FixtureRequest) -> Boundary:
    obj: Boundary = request.getfixturevalue(request.param)
    return obj


def test_changelist_lists_the_boundary(admin_client: Client, boundary: Boundary) -> None:
    response = admin_client.get(admin_url(boundary, "changelist"))

    assert response.status_code == 200
    assert boundary in response.context["cl"].result_list


def test_change_view_summarizes_the_geometry(admin_client: Client, boundary: Boundary) -> None:
    response = admin_client.get(admin_url(boundary, "change", boundary.pk))

    assert response.status_code == 200
    content = response.content.decode()
    assert "polygon(s)" in content
    assert "MULTIPOLYGON" not in content


def test_boundary_cannot_be_added_changed_or_deleted(
    admin_client: Client, boundary: Boundary
) -> None:
    assert admin_client.get(admin_url(boundary, "add")).status_code == 403
    assert admin_client.post(admin_url(boundary, "change", boundary.pk), {}).status_code == 403
    assert (
        admin_client.post(admin_url(boundary, "delete", boundary.pk), {"post": "yes"}).status_code
        == 403
    )


def test_block_change_view_shows_its_place_and_county_subdivision(
    admin_client: Client, block: Block
) -> None:
    response = admin_client.get(admin_url(block, "change", block.pk))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Columbus city (3918000)" in content
    assert "Columbus city (3904918000)" in content
