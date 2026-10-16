from bdc.models import Release
from geography.models import Block, State
from served_unserved.models import Rollup, RollupLevel, ServedStatus
from served_unserved.release_states import delete_state, holds_state, states_in_release
from served_unserved.rollups import build_rollups


def add_wv_status(release: Release, block: Block, cell: str) -> ServedStatus:
    """A West Virginia status, location 2001, served by any technology only."""
    return ServedStatus.objects.create(
        release=release,
        location_id=2001,
        block=block,
        h3_res8=cell,
        any_100_20=True,
        wired_100_20=False,
        terrestrial_100_20=False,
    )


def test_holds_state(served_status: ServedStatus) -> None:
    assert holds_state(served_status.release, "39") is True
    assert holds_state(served_status.release, "54") is False


def test_states_in_release(served_status: ServedStatus, wv_block: Block) -> None:
    release = served_status.release

    assert [state.geoid for state in states_in_release(release)] == ["39"]

    add_wv_status(release, wv_block, "882a8a6c13fffff")

    assert [state.geoid for state in states_in_release(release)] == ["39", "54"]


def test_release_without_statuses_holds_no_state(release: Release, state: State) -> None:
    assert states_in_release(release) == []


def test_delete_state_keeps_the_release_and_other_states(
    served_status: ServedStatus, wv_block: Block
) -> None:
    release = served_status.release
    add_wv_status(release, wv_block, served_status.h3_res8)
    for state_fips in ("39", "54"):
        for level in RollupLevel:
            build_rollups(release, state_fips, level)
    wv_rows = list(Rollup.objects.filter(state_id="54").order_by("id").values_list())

    assert delete_state(release, "39") == (1, 7)

    assert list(ServedStatus.objects.values_list("location_id", flat=True)) == [2001]
    assert list(Rollup.objects.order_by("id").values_list()) == wv_rows
    assert Release.objects.filter(pk=release.pk).exists()
