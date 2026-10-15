from django.contrib import admin

from bdc.models import Release
from core.admin import ReadOnlyModelAdmin


@admin.register(Release)
class ReleaseAdmin(ReadOnlyModelAdmin):
    list_display = ("__str__", "filing_period", "as_of", "processed_on")
