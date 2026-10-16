"""Readers retain one snapshot without blocking committed data writers."""

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from django.db import close_old_connections, connection, transaction
from rest_framework.test import APIClient

from bdc.api.queries import release_metadata
from bdc.models import Release
from geography.models import Block
from served_unserved.api import views
from served_unserved.models import Rollup, ServedStatus

pytestmark = pytest.mark.django_db(transaction=True)
URL = "/api/v1/served-unserved/rollups/"


@pytest.mark.parametrize("operation", ["replace", "delete", "add_state", "rebuild"])
def test_request_snapshot_during_committed_change(
    rollup: Rollup,
    served_status: ServedStatus,
    wv_block: Block,
    operation: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_id = rollup.release_id
    wv_block_id = wv_block.pk

    def write() -> None:
        close_old_connections()
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout = '5s'")
                    cursor.execute("SET LOCAL statement_timeout = '8s'")
                if operation in {"replace", "delete"}:
                    Release.objects.get(pk=release_id).delete()
                if operation == "replace":
                    new = Release.objects.create(
                        filing_period="D25", as_of="2025-12-31", processed_on="2026-09-29"
                    )
                    Rollup.objects.create(
                        release=new,
                        state_id="39",
                        level="county",
                        code="39049",
                        locations=20,
                        any_100_20=20,
                        wired_100_20=20,
                        terrestrial_100_20=20,
                    )
                elif operation == "rebuild":
                    Rollup.objects.filter(pk=rollup.pk).update(wired_100_20=5)
                elif operation == "add_state":
                    ServedStatus.objects.create(
                        release_id=release_id,
                        block_id=wv_block_id,
                        location_id=2,
                        h3_res8="882a91ae3bfffff",
                        any_100_20=True,
                        wired_100_20=True,
                        terrestrial_100_20=True,
                    )
                    Rollup.objects.create(
                        release_id=release_id,
                        state_id="54",
                        level="county",
                        code="54009",
                        locations=1,
                        any_100_20=1,
                        wired_100_20=1,
                        terrestrial_100_20=1,
                    )
        finally:
            connection.close()

    def between_reads(release: Release) -> dict[str, Any]:
        metadata = release_metadata(release)
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(write).result(timeout=10)
        return metadata

    monkeypatch.setattr(views, "release_metadata", between_reads)
    response = APIClient().get(URL, {"level": "county"})
    assert response.status_code == 200
    assert response.json()["results"][0]["wired_100_20"] == 4
    assert response.json()["count"] == 1
    assert len(response.json()["release"]["states"]) == 1
    monkeypatch.setattr(views, "release_metadata", release_metadata)
    next_response = APIClient().get(URL, {"level": "county"})
    if operation == "delete":
        assert next_response.status_code == 404
    else:
        data = next_response.json()
        assert data["count"] == (2 if operation == "add_state" else 1)
        assert (
            data["results"][0]["wired_100_20"]
            == {
                "replace": 20,
                "rebuild": 5,
                "add_state": 4,
            }[operation]
        )
