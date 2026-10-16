import pytest
from django.test import Client
from django.urls import reverse

from bdc.models import Release
from geography.models import State
from served_unserved.models import Rollup, ServedStatus

CHANGELIST = "admin:served_unserved_servedstatus_changelist"
ROLLUPS = "admin:served_unserved_rollup_changelist"


def test_changelist_lists_the_status(admin_client: Client, served_status: ServedStatus) -> None:
    response = admin_client.get(reverse(CHANGELIST))

    assert response.status_code == 200
    assert served_status in response.context["cl"].result_list


def test_changelist_shows_the_block_and_cell(
    admin_client: Client, served_status: ServedStatus
) -> None:
    response = admin_client.get(reverse(CHANGELIST))

    assert response.status_code == 200
    assert "390490001101000" in response.text
    assert "882a91ae3bfffff" in response.text


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


def test_rollup_changelist_lists_the_rollup(admin_client: Client, rollup: Rollup) -> None:
    response = admin_client.get(reverse(ROLLUPS))

    assert response.status_code == 200
    assert rollup in response.context["cl"].result_list


def test_rollup_change_view_opens(admin_client: Client, rollup: Rollup) -> None:
    url = reverse("admin:served_unserved_rollup_change", args=[rollup.pk])

    assert admin_client.get(url).status_code == 200


def test_rollup_cannot_be_added_changed_or_deleted(admin_client: Client, rollup: Rollup) -> None:
    add = reverse("admin:served_unserved_rollup_add")
    change = reverse("admin:served_unserved_rollup_change", args=[rollup.pk])
    delete = reverse("admin:served_unserved_rollup_delete", args=[rollup.pk])

    assert admin_client.get(add).status_code == 403
    assert admin_client.post(change, {}).status_code == 403
    assert admin_client.post(delete, {"post": "yes"}).status_code == 403


def test_search_by_code_finds_the_rollup(admin_client: Client, rollup: Rollup) -> None:
    response = admin_client.get(reverse(ROLLUPS), {"q": "39049"})

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == [rollup]


def test_search_by_h3_cell_finds_the_rollup(
    admin_client: Client, release: Release, state: State
) -> None:
    cell = Rollup.objects.create(
        release=release,
        state=state,
        level="h3_res8",
        code="882a91ae3bfffff",
        locations=10,
        any_100_20=8,
        wired_100_20=4,
        terrestrial_100_20=6,
    )

    response = admin_client.get(reverse(ROLLUPS), {"q": "882a91ae3bfffff"})

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == [cell]


def test_rollup_changelist_shows_the_state(
    admin_client: Client, release: Release, state: State, wv_state: State
) -> None:
    for each in (state, wv_state):
        Rollup.objects.create(
            release=release,
            state=each,
            level="h3_res8",
            code="882a91ae3bfffff",
            locations=10,
            any_100_20=8,
            wired_100_20=4,
            terrestrial_100_20=6,
        )

    response = admin_client.get(reverse(ROLLUPS))

    assert response.status_code == 200
    assert '<td class="field-state_id">39</td>' in response.text
    assert '<td class="field-state_id">54</td>' in response.text


# The search is an exact match, so a prefix finds nothing.
@pytest.mark.parametrize("term", ["3904", "abc"])
def test_rollup_search_matches_the_whole_code(
    admin_client: Client, rollup: Rollup, term: str
) -> None:
    response = admin_client.get(reverse(ROLLUPS), {"q": term})

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == []
