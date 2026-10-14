import pytest
from django.db.models import Model
from django.test import Client
from django.urls import reverse

from bdc.models import Location


def admin_url(obj: Model, view: str, *args: object) -> str:
    return reverse(f"admin:{obj._meta.app_label}_{obj._meta.model_name}_{view}", args=args)


@pytest.fixture(params=["release", "location"])
def record(request: pytest.FixtureRequest) -> Model:
    obj: Model = request.getfixturevalue(request.param)
    return obj


def test_changelist_lists_the_record(admin_client: Client, record: Model) -> None:
    response = admin_client.get(admin_url(record, "changelist"))

    assert response.status_code == 200
    assert record in response.context["cl"].result_list


def test_change_view_opens(admin_client: Client, record: Model) -> None:
    response = admin_client.get(admin_url(record, "change", record.pk))

    assert response.status_code == 200


def test_record_cannot_be_added_changed_or_deleted(admin_client: Client, record: Model) -> None:
    assert admin_client.get(admin_url(record, "add")).status_code == 403
    assert admin_client.post(admin_url(record, "change", record.pk), {}).status_code == 403
    assert (
        admin_client.post(admin_url(record, "delete", record.pk), {"post": "yes"}).status_code
        == 403
    )


@pytest.mark.parametrize("term", ["1000338835", "882a91ae3bfffff", "390490001101000"])
def test_location_search_finds_the_location(
    admin_client: Client, location: Location, term: str
) -> None:
    response = admin_client.get(admin_url(location, "changelist"), {"q": term})

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == [location]


# "²" passes str.isdigit() but int() rejects it.
@pytest.mark.parametrize("term", ["not-a-number", "²"])
def test_location_search_for_unknown_text_finds_nothing(
    admin_client: Client, location: Location, term: str
) -> None:
    response = admin_client.get(admin_url(location, "changelist"), {"q": term})

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == []
