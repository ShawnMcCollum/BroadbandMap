from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from served_unserved.models import Rollup, ServedStatus


def test_build_rollups_rebuilds_every_release(served_status: ServedStatus) -> None:
    out = StringIO()

    call_command("build_rollups", stdout=out)

    assert "Built 1 rollups for December 2025 (processed 2026-09-29)." in out.getvalue()
    rollup = Rollup.objects.get()
    assert rollup.code == "39049"
    counts = (rollup.locations, rollup.any_100_20, rollup.wired_100_20, rollup.terrestrial_100_20)
    assert counts == (1, 1, 1, 1)


def test_build_rollups_needs_a_release(db: None) -> None:
    with pytest.raises(CommandError, match="no release is loaded"):
        call_command("build_rollups")
