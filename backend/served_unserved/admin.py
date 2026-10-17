import re

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from bdc.models import Release
from core.admin import CappedCountPaginator, ReadOnlyModelAdmin
from served_unserved.models import AREA_KEYS, Rollup, RollupLevel, ServedStatus


def status_lookup(term: str) -> dict[str, object] | None:
    """The ServedStatus lookup that a search term names, or None if it names nothing.

    A term of 15 digits is a block GEOID, and one of 15 lowercase hex characters an H3 cell
    index, in the forms of their rollup codes. Any other decimal term is a location ID. A block
    GEOID is tried first, since its digits are also hex. No FCC location ID has 15 digits, and
    every resolution-8 cell index ends in "fffff" (ADR 0023).
    """
    for level in (RollupLevel.BLOCK, RollupLevel.H3_RES8):
        key = AREA_KEYS[level]
        if re.fullmatch(key.pattern, term):
            return {key.lookup: term}
    if term.isdecimal():
        return {"location_id": int(term)}
    return None


@admin.register(ServedStatus)
class ServedStatusAdmin(ReadOnlyModelAdmin):
    # block_id shows the GEOID without fetching each block and its geometry.
    list_display = (
        "location_id",
        "release",
        "block_id",
        "h3_res8",
        "any_100_20",
        "wired_100_20",
        "terrestrial_100_20",
    )
    list_filter = ("release", "any_100_20", "wired_100_20", "terrestrial_100_20")
    list_select_related = ("release",)
    # The statuses are listed by release ID, then location ID (ServedStatus.Meta.ordering), the
    # order of the unique (release, location_id) index. No column sorts the list, since no index
    # serves any other order (ADR 0022).
    sortable_by = ()
    # The count stops after CappedCountPaginator.cap statuses, and the filters do not count their
    # choices: either would read every status in the table or the release (ADR 0022).
    paginator = CappedCountPaginator
    show_facets = admin.ShowFacets.NEVER
    # search_fields makes the search box render; get_search_results does the search.
    search_fields = ("location_id",)
    search_help_text = (
        "Location ID, block GEOID (15 digits) or H3 cell index (15 lowercase hex characters)"
    )

    def get_search_results(
        self, request: HttpRequest, queryset: QuerySet[ServedStatus], search_term: str
    ) -> tuple[QuerySet[ServedStatus], bool]:
        term = search_term.strip()
        if not term:
            return queryset, False
        lookup = status_lookup(term)
        if lookup is None:
            return queryset.none(), False
        # Naming every release lets an index that leads with the release find the location, block
        # or cell with one probe per release: nothing indexes location_id, block_id or h3_res8
        # alone (ADRs 0021 and 0023).
        releases = list(Release.objects.order_by().values_list("pk", flat=True))
        return queryset.filter(release_id__in=releases, **lookup), False


@admin.register(Rollup)
class RollupAdmin(ReadOnlyModelAdmin):
    list_display = (
        "code",
        "level",
        "state_id",
        "release",
        "locations",
        "any_100_20",
        "wired_100_20",
        "terrestrial_100_20",
    )
    list_filter = ("level", "release")
    list_select_related = ("release",)
    # The rollups are listed by release ID, level, code, then state ID (Rollup.Meta.ordering), the
    # order of the unique (release, level, code, state) index. No column sorts the list, since no
    # index serves any other order (ADR 0024).
    sortable_by = ()
    # The count stops after CappedCountPaginator.cap rollups, and the filters do not count their
    # choices: either would read every rollup in the table or the release (ADRs 0022 and 0024).
    paginator = CappedCountPaginator
    show_facets = admin.ShowFacets.NEVER
    # search_fields makes the search box render; get_search_results does the search.
    search_fields = ("code",)
    search_help_text = "Area code: GEOID or H3 cell index"

    def get_queryset(self, request: HttpRequest) -> QuerySet[Rollup]:
        # Naming every release lets the unique index go straight to a level, or a level and code,
        # in each release. Without them, a filter on a level reads past the rollups of every level
        # before it, in each release (ADR 0024).
        releases = list(Release.objects.order_by().values_list("pk", flat=True))
        return super().get_queryset(request).filter(release_id__in=releases)

    def get_search_results(
        self, request: HttpRequest, queryset: QuerySet[Rollup], search_term: str
    ) -> tuple[QuerySet[Rollup], bool]:
        term = search_term.strip()
        if not term:
            return queryset, False
        # Each level whose codes have the term's form, so that the unique index finds the code
        # with one probe per release and level (ADR 0024)
        levels = [level for level, key in AREA_KEYS.items() if re.fullmatch(key.pattern, term)]
        if not levels:
            return queryset.none(), False
        return queryset.filter(level__in=levels, code=term), False
