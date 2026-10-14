import pytest
from django.test import Client
from django.urls import reverse

from served_unserved.models import ServedStatus

CHANGELIST = "admin:served_unserved_servedstatus_changelist"


def test_changelist_lists_the_status(admin_client: Client, served_status: ServedStatus) -> None:
    response = admin_client.get(reverse(CHANGELIST))

    assert response.status_code == 200
    assert served_status in response.context["cl"].result_list


def test_change_view_opens(admin_client: Client, served_status: ServedStatus) -> None:
    url = reverse("admin:served_unserved_servedstatus_change", args=[served_status.pk])

    assert admin_client.get(url).status_code == 200


def test_status_cannot_be_added_changed_or_deleted(
    admin_client: Client, served_status: ServedStatus
) -> None:
    add = reverse("admin:served_unserved_servedstatus_add")
    change = reverse("admin:served_unserved_servedstatus_change", args=[served_status.pk])
    delete = reverse("admin:served_unserved_servedstatus_delete", args=[served_status.pk])

    assert admin_client.get(add).status_code == 403
    assert admin_client.post(change, {}).status_code == 403
    assert admin_client.post(delete, {"post": "yes"}).status_code == 403


def test_search_by_location_id_finds_the_status(
    admin_client: Client, served_status: ServedStatus
) -> None:
    response = admin_client.get(reverse(CHANGELIST), {"q": "1000338835"})

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == [served_status]


# "²" passes str.isdigit() but int() rejects it.
@pytest.mark.parametrize("term", ["abc", "²"])
def test_search_for_text_finds_nothing(
    admin_client: Client, served_status: ServedStatus, term: str
) -> None:
    response = admin_client.get(reverse(CHANGELIST), {"q": term})

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == []
