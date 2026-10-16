from django.test import Client
from django.urls import reverse

from bdc.models import Release
from geography.models import Block
from served_unserved.models import ServedStatus


def test_changelist_lists_the_release(admin_client: Client, release: Release) -> None:
    response = admin_client.get(reverse("admin:bdc_release_changelist"))

    assert response.status_code == 200
    assert release in response.context["cl"].result_list


def test_change_view_opens(admin_client: Client, release: Release) -> None:
    url = reverse("admin:bdc_release_change", args=[release.pk])

    assert admin_client.get(url).status_code == 200


def test_release_cannot_be_added_changed_or_deleted(admin_client: Client, release: Release) -> None:
    add = reverse("admin:bdc_release_add")
    change = reverse("admin:bdc_release_change", args=[release.pk])
    delete = reverse("admin:bdc_release_delete", args=[release.pk])

    assert admin_client.get(add).status_code == 403
    assert admin_client.post(change, {}).status_code == 403
    assert admin_client.post(delete, {"post": "yes"}).status_code == 403


def test_changelist_lists_the_states(
    admin_client: Client, served_status: ServedStatus, wv_block: Block
) -> None:
    ServedStatus.objects.create(
        release=served_status.release,
        location_id=2001,
        block=wv_block,
        h3_res8="882a8a6c13fffff",
        any_100_20=True,
        wired_100_20=False,
        terrestrial_100_20=False,
    )

    response = admin_client.get(reverse("admin:bdc_release_changelist"))

    assert response.status_code == 200
    assert '<td class="field-states">OH, WV</td>' in response.text
