from django.urls import path

from geography.api.views import Counties

urlpatterns = [path("geographies/county/", Counties.as_view(), name="county-geojson")]
