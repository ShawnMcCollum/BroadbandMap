from django.contrib import admin

from bdc.models import Release
from core.admin import ReadOnlyModelAdmin
from served_unserved.release_states import states_in_release


@admin.register(Release)
class ReleaseAdmin(ReadOnlyModelAdmin):
    list_display = ("__str__", "filing_period", "as_of", "processed_on", "states")

    @admin.display(description="States")
    def states(self, release: Release) -> str:
        """The states the release holds, by abbreviation, e.g. "OH, WV"."""
        return ", ".join(state.abbreviation for state in states_in_release(release))
