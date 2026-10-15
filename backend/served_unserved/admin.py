from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from core.admin import ReadOnlyModelAdmin
from served_unserved.models import Rollup, ServedStatus


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
    # search_fields makes the search box render; get_search_results does the search.
    search_fields = ("location_id",)
    search_help_text = "Location ID"

    def get_search_results(
        self, request: HttpRequest, queryset: QuerySet[ServedStatus], search_term: str
    ) -> tuple[QuerySet[ServedStatus], bool]:
        term = search_term.strip()
        if not term:
            return queryset, False
        if term.isdecimal():
            return queryset.filter(location_id=int(term)), False
        return queryset.none(), False


@admin.register(Rollup)
class RollupAdmin(ReadOnlyModelAdmin):
    list_display = (
        "code",
        "level",
        "release",
        "locations",
        "any_100_20",
        "wired_100_20",
        "terrestrial_100_20",
    )
    list_filter = ("level", "release")
    list_select_related = ("release",)
    # search_fields makes the search box render; get_search_results does the search.
    search_fields = ("code",)
    search_help_text = "Area code: GEOID or H3 cell index"

    def get_search_results(
        self, request: HttpRequest, queryset: QuerySet[Rollup], search_term: str
    ) -> tuple[QuerySet[Rollup], bool]:
        term = search_term.strip()
        if not term:
            return queryset, False
        return queryset.filter(code=term), False
