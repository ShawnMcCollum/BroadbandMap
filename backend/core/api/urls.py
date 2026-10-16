"""Version 1 business API routes, composed by the project URL configuration."""

from django.urls import include, path

app_name = "api_v1"

urlpatterns = [
    path("", include("bdc.api.urls")),
    path("", include("geography.api.urls")),
    path("", include("served_unserved.api.urls")),
    path("", include("natural_language.api.urls")),
]
