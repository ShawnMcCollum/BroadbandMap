from django.urls import path

from served_unserved.api.views import Locations, Rollups

urlpatterns = [
    path("served-unserved/rollups/", Rollups.as_view(), name="rollups"),
    path("served-unserved/locations/", Locations.as_view(), name="locations"),
]
