"""Served/Unserved status of each location in each FCC release."""

from django.db import models


class ServedStatus(models.Model):
    """A location's 100/20 Mbps status in one release."""

    release = models.ForeignKey(
        "bdc.Release",
        on_delete=models.CASCADE,
        related_name="served_statuses",
        db_index=False,
    )
    location = models.ForeignKey(
        "bdc.Location", on_delete=models.PROTECT, related_name="served_statuses"
    )
    any_100_20 = models.BooleanField(
        help_text="100/20 Mbps available by any technology, including satellite."
    )
    wired_100_20 = models.BooleanField(
        help_text="100/20 Mbps available by wired technology (fiber, cable, copper)."
    )
    terrestrial_100_20 = models.BooleanField(
        help_text="100/20 Mbps available by wired or fixed wireless technology."
    )

    class Meta:
        verbose_name = "served status"
        verbose_name_plural = "served statuses"
        ordering = ["release", "location"]
        constraints = [
            models.UniqueConstraint(
                fields=["release", "location"], name="served_unserved_unique_location_per_release"
            ),
            models.CheckConstraint(
                condition=models.Q(wired_100_20=False) | models.Q(terrestrial_100_20=True),
                name="served_unserved_wired_implies_terrestrial",
            ),
            models.CheckConstraint(
                condition=models.Q(terrestrial_100_20=False) | models.Q(any_100_20=True),
                name="served_unserved_terrestrial_implies_any",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.location_id} in {self.release}"
