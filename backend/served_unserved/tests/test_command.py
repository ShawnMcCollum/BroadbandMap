import re
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from pytest import MonkeyPatch

from bdc.models import Release
from core.tests.helpers import table_stats
from geography.models import Block
from served_unserved.models import Rollup, ServedStatus
from served_unserved.rollups import COUNT_FIELDS, build_rollups


def test_build_rollups_rebuilds_every_release(served_status: ServedStatus) -> None:
    out = StringIO()

    call_command("build_rollups", stdout=out)

    assert "Built 7 rollups for December 2025 (processed 2026-09-29)." in out.getvalue()
    rows = sorted(Rollup.objects.values_list("level", "code", *COUNT_FIELDS))
    assert rows == [
        ("block", "390490001101000", 1, 1, 1, 1),
        ("block_group", "390490001101", 1, 1, 1, 1),
        ("county", "39049", 1, 1, 1, 1),
        ("county_subdivision", "3904918000", 1, 1, 1, 1),
        ("h3_res8", "882a91ae3bfffff", 1, 1, 1, 1),
        ("place", "3918000", 1, 1, 1, 1),
        ("tract", "39049000110", 1, 1, 1, 1),
    ]


@pytest.mark.django_db(transaction=True)
def test_build_rollups_vacuums_and_analyzes_the_rollups(served_status: ServedStatus) -> None:
    before = table_stats((Rollup, ServedStatus))
    out = StringIO()

    call_command("build_rollups", stdout=out)

    after = table_stats((Rollup, ServedStatus))
    assert re.fullmatch(r"Vacuumed and analyzed 1 table in \d+ s", out.getvalue().splitlines()[-1])
    rollups, statuses = "served_unserved_rollup", "served_unserved_servedstatus"
    assert after[rollups].vacuum_count == before[rollups].vacuum_count + 1
    assert after[rollups].analyzed_after_vacuum()
    assert after[statuses].vacuum_count == before[statuses].vacuum_count


def test_build_rollups_needs_a_release(db: None) -> None:
    with pytest.raises(CommandError, match="no release is loaded"):
        call_command("build_rollups")


def test_build_rollups_needs_assigned_blocks(served_status: ServedStatus) -> None:
    Block.objects.update(county_subdivision=None)

    with pytest.raises(CommandError, match="some census blocks have no county subdivision"):
        call_command("build_rollups")

    assert Rollup.objects.count() == 0


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
