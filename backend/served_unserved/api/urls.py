from django.urls import path

from served_unserved.api.views import Rollups

urlpatterns = [path("served-unserved/rollups/", Rollups.as_view(), name="rollups")]
