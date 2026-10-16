"""Invalidate traversals in the same transaction as a release write."""

from django.db.models import F

from bdc.models import Release


def advance_generation(release: Release) -> None:
    """Call under the writer guard, inside the transaction changing this release.

    The release ID also binds cursors, so deleting and recreating a release cannot
    reuse an earlier generation. A rollback preserves both the data and generation.
    """
    Release.objects.filter(pk=release.pk).update(data_generation=F("data_generation") + 1)
