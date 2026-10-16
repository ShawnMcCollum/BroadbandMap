"""FCC Broadband Data Collection releases."""

from django.db import models


class Release(models.Model):
    """One version of an FCC data release."""

    filing_period = models.CharField(
        max_length=3,
        help_text='FCC filing period: J (June) or D (December) and a two-digit year, e.g. "D25".',
    )
    as_of = models.DateField(help_text="Date the availability data describes, e.g. 2025-12-31.")
    processed_on = models.DateField(help_text="Date the FCC processed this version of the release.")
    data_generation = models.PositiveBigIntegerField(
        default=1,
        help_text="Internal cursor generation, advanced by every committed release writer.",
    )

    class Meta:
        # The API's release list and its default, latest release follow this order (ADR 0013,
        # decision 6). A model ordered by "release" joins this table and sorts by it, which no
        # index serves; order by "release_id" instead (ADR 0022).
        ordering = ["-as_of", "-processed_on"]
        constraints = [
            models.UniqueConstraint(
                fields=["as_of", "processed_on"], name="bdc_release_unique_version"
            ),
            models.CheckConstraint(
                condition=models.Q(filing_period__regex=r"^[JD][0-9]{2}$"),
                name="bdc_release_filing_period_format",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.as_of:%B %Y} (processed {self.processed_on:%Y-%m-%d})"
