from dataclasses import replace

from selection import Selection, Snapshot
from summaries import CountySummaries, Release


def test_changes_and_obsolete_response(release: Release) -> None:
    snapshot = Snapshot()
    snapshot.reconcile((release,))
    requested = snapshot.selection
    data = CountySummaries(release, "wired", ())
    assert snapshot.accept(requested, data)
    snapshot.choose_county("39001")
    snapshot.diagnosis = "old detail"
    snapshot.choose_county("39003")
    assert snapshot.diagnosis is None
    assert snapshot.summaries is data
    snapshot.change(release=release.key, flag="any")
    assert snapshot.selection.county is None
    assert snapshot.summaries is None
    assert not snapshot.accept(requested, data)


def test_refresh_preserves_pair_and_disappearance_requires_choice(release: Release) -> None:
    snapshot = Snapshot()
    snapshot.reconcile((release,))
    snapshot.change(release=release.key, flag="terrestrial")
    for _ in range(20):
        snapshot.names = {"39001": "Adams"}
        snapshot.summaries = CountySummaries(release, "terrestrial", ())
        snapshot.refresh()
        assert snapshot.names is None
        assert snapshot.summaries is None
        assert snapshot.releases is None
        assert snapshot.selection == Selection(release=release.key, flag="terrestrial")
    other = replace(release, processed_on="2026-10-01")
    snapshot.reconcile((other,))
    assert snapshot.selection.release is None
    assert snapshot.needs_selection
    snapshot.reconcile((other,))
    assert snapshot.selection.release is None


def test_newest_processing_even_without_ohio(release: Release) -> None:
    newest = replace(release, processed_on="2026-10-01", states=())
    snapshot = Snapshot()
    snapshot.reconcile((release, newest))
    assert snapshot.selection.release == newest.key
