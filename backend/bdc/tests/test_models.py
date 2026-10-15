from datetime import date

import pytest
from django.db import IntegrityError, transaction

from bdc.models import Release


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
