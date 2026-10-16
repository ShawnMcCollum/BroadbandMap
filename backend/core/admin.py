from typing import cast

from django.contrib import admin
from django.core.paginator import Paginator
from django.db.models import Model, QuerySet
from django.http import HttpRequest
from django.utils.functional import cached_property


class ReadOnlyModelAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin for loader-owned data: viewable, never added, changed or deleted."""

    show_full_result_count = False

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Model | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Model | None = None) -> bool:
        return False


class CappedCountPaginator(Paginator):  # type: ignore[type-arg]
    """Pages a changelist without counting more than ``cap`` of its rows (ADR 0022).

    Counting every row of a loaded table reads all of them. This count stops after ``cap`` + 1
    rows, and only the first ``cap`` rows are offered as pages. ``capped`` says whether there are
    more, so the changelist can say so. ``cap`` must exceed the admin's ``list_per_page`` and
    ``list_max_show_all``, since the admin shows a list it does not page in full.
    """

    cap = 10_000

    @cached_property
    def _found(self) -> int:
        # The admin pages a QuerySet. Unordered, the count can stop at the first rows it finds.
        rows = cast("QuerySet[Model]", self.object_list)
        return rows.order_by()[: self.cap + 1].count()

    @cached_property
    def count(self) -> int:
        return min(self._found, self.cap)

    @property
    def capped(self) -> bool:
        return self._found > self.cap
