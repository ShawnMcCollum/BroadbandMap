from django.urls import path

from natural_language.api.views import (
    NaturalLanguageConfiguration,
    NaturalLanguageQuery,
    NaturalLanguageStatus,
)

urlpatterns = [
    path("natural-language/", NaturalLanguageStatus.as_view(), name="natural-language-status"),
    path(
        "natural-language/configuration/",
        NaturalLanguageConfiguration.as_view(),
        name="natural-language-configuration",
    ),
    path("natural-language/query/", NaturalLanguageQuery.as_view(), name="natural-language-query"),
]
