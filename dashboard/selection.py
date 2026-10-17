"""One selection owner and one current transient snapshot per Streamlit session."""

from dataclasses import dataclass, field, replace

from summaries import CountySummaries, Flag, Release, ReleaseKey


@dataclass(frozen=True)
class Selection:
    release: ReleaseKey | None = None
    state: str = "39"
    flag: Flag = "wired"
    county: str | None = None


@dataclass
class Snapshot:
    selection: Selection = field(default_factory=Selection)
    releases: tuple[Release, ...] | None = None
    names: dict[str, str] | None = None
    summaries: CountySummaries | None = None
    diagnosis: str | None = None
    errors: dict[str, str] = field(default_factory=dict)
    needs_selection: bool = False
    initialized: bool = False

    def change(self, *, release: ReleaseKey | None, flag: Flag) -> None:
        if (release, flag) != (self.selection.release, self.selection.flag):
            self.selection = Selection(release=release, flag=flag)
            self.summaries = None
            self.diagnosis = None
            self.errors.pop("summaries", None)
            self.errors.pop("diagnosis", None)

    def choose_county(self, county: str | None) -> None:
        if county != self.selection.county:
            self.selection = replace(self.selection, county=county)
            self.diagnosis = None
            self.errors.pop("diagnosis", None)

    def refresh(self) -> None:
        self.releases = None
        self.names = None
        self.summaries = None
        self.diagnosis = None
        self.errors.clear()

    def reconcile(self, releases: tuple[Release, ...]) -> None:
        self.releases = releases
        keys = {release.key for release in releases}
        if self.selection.release is not None and self.selection.release not in keys:
            self.change(release=None, flag=self.selection.flag)
            self.needs_selection = True
        elif not self.initialized and releases:
            self.change(release=max(releases, key=lambda r: r.key).key, flag=self.selection.flag)
        self.initialized = self.initialized or bool(releases)

    def accept(self, requested: Selection, data: CountySummaries) -> bool:
        if (
            requested == self.selection
            and data.release.key == requested.release
            and data.flag == requested.flag
        ):
            self.summaries = data
            return True
        return False
