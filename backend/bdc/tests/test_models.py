from datetime import date

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError

from bdc.models import Location, Release
from geography.models import Block


def test_release_version_must_be_unique(release: Release) -> None:
    with (
        pytest.raises(IntegrityError, match="bdc_release_unique_version"),
        transaction.atomic(),
    ):
        Release.objects.create(
            filing_period="D25", as_of=release.as_of, processed_on=release.processed_on
        )


def test_release_can_be_reprocessed_on_another_date(release: Release) -> None:
    Release.objects.create(
        filing_period="D25", as_of=release.as_of, processed_on=date(2026, 10, 14)
    )

    assert Release.objects.count() == 2


@pytest.mark.parametrize("filing_period", ["X25", "D2"])
@pytest.mark.django_db
def test_invalid_filing_period_is_rejected(filing_period: str) -> None:
    with (
        pytest.raises(IntegrityError, match="bdc_release_filing_period_format"),
        transaction.atomic(),
    ):
        Release.objects.create(
            filing_period=filing_period, as_of=date(2025, 12, 31), processed_on=date(2026, 9, 29)
        )


@pytest.mark.parametrize("filing_period", ["D25", "J25"])
@pytest.mark.django_db
def test_valid_filing_period_is_accepted(filing_period: str) -> None:
    Release.objects.create(
        filing_period=filing_period, as_of=date(2025, 12, 31), processed_on=date(2026, 9, 29)
    )

    assert Release.objects.count() == 1


def test_str_names_the_month_and_processing_date(release: Release) -> None:
    assert str(release) == "December 2025 (processed 2026-09-29)"


@pytest.mark.parametrize("h3_res8", ["882A91AE3BFFFFF", "882a91ae3bffff"])
def test_invalid_h3_cell_is_rejected(block: Block, h3_res8: str) -> None:
    with (
        pytest.raises(IntegrityError, match="bdc_location_h3_res8_format"),
        transaction.atomic(),
    ):
        Location.objects.create(location_id=1, block=block, h3_res8=h3_res8)


@pytest.mark.django_db
def test_location_in_a_missing_block_is_rejected() -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        Location.objects.create(
            location_id=1, block_id="390490001101999", h3_res8="882a91ae3bfffff"
        )
        connection.check_constraints()


def test_block_with_a_location_cannot_be_deleted(block: Block, location: Location) -> None:
    with pytest.raises(ProtectedError):
        block.delete()
