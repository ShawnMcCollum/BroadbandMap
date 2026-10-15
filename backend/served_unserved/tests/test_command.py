from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from pytest import MonkeyPatch

from bdc.models import Release
from served_unserved.models import Rollup, ServedStatus
from served_unserved.rollups import COUNT_FIELDS, build_rollups


def test_build_rollups_rebuilds_every_release(served_status: ServedStatus) -> None:
    out = StringIO()

    call_command("build_rollups", stdout=out)

    assert "Built 5 rollups for December 2025 (processed 2026-09-29)." in out.getvalue()
    rows = sorted(Rollup.objects.values_list("level", "code", *COUNT_FIELDS))
    assert rows == [
        ("block", "390490001101000", 1, 1, 1, 1),
        ("block_group", "390490001101", 1, 1, 1, 1),
        ("county", "39049", 1, 1, 1, 1),
        ("h3_res8", "882a91ae3bfffff", 1, 1, 1, 1),
        ("tract", "39049000110", 1, 1, 1, 1),
    ]


def test_build_rollups_needs_a_release(db: None) -> None:
    with pytest.raises(CommandError, match="no release is loaded"):
        call_command("build_rollups")


def test_failed_rebuild_keeps_the_previous_rollups(
    served_status: ServedStatus, rollup: Rollup, monkeypatch: MonkeyPatch
) -> None:
    def fail_at_blocks(release: Release, level: str) -> int:
        if level == "block":
            raise RuntimeError("block build failed")
        return build_rollups(release, level)

    monkeypatch.setattr(
        "served_unserved.management.commands.build_rollups.build_rollups", fail_at_blocks
    )

    with pytest.raises(RuntimeError, match="block build failed"):
        call_command("build_rollups")

    # The county and tract levels were rebuilt before the failure, then rolled back.
    assert list(Rollup.objects.values_list("level", "code", "locations")) == [
        ("county", "39049", 10)
    ]
