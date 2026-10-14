from django.contrib import admin
from django.db.models import Q, QuerySet
from django.http import HttpRequest

from bdc.models import Location, Release
from core.admin import ReadOnlyModelAdmin


@admin.register(Release)
class ReleaseAdmin(ReadOnlyModelAdmin):
    list_display = ("__str__", "filing_period", "as_of", "processed_on")


@admin.register(Location)
class LocationAdmin(ReadOnlyModelAdmin):
    list_display = ("location_id", "block_id", "h3_res8")
    # The default "=location_id" search fails on non-numeric input, and a contains search
    # scans 4.5M rows. get_search_results uses exact, indexed lookups instead;
    # search_fields only makes the search box render.
    search_fields = ("location_id",)
    search_help_text = "Location ID, block GEOID or H3 cell"

    def get_search_results(
        self, request: HttpRequest, queryset: QuerySet[Location], search_term: str
    ) -> tuple[QuerySet[Location], bool]:
        term = search_term.strip()
        if not term:
            return queryset, False
        query = Q(block_id=term) | Q(h3_res8=term.lower())
        if term.isdecimal():
            query |= Q(location_id=int(term))
        return queryset.filter(query), False
