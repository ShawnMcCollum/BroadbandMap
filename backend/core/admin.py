from django.contrib import admin
from django.db.models import Model
from django.http import HttpRequest


class ReadOnlyModelAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin for loader-owned data: viewable, never added, changed or deleted."""

    show_full_result_count = False

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Model | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Model | None = None) -> bool:
        return False
