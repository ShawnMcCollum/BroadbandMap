from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularJSONAPIView
from rest_framework.permissions import AllowAny

from core.views import health


class PublicSchemaView(SpectacularJSONAPIView):
    authentication_classes: list[type] = []
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]
    urlconf = "config.urls"


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/schema/", PublicSchemaView.as_view(), name="api-schema"),
    path("api/v1/", include(("core.api.urls", "api_v1"), namespace="api_v1")),
]
