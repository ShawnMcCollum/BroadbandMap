from django.urls import path

from bdc.api.views import Releases

urlpatterns = [path("releases/", Releases.as_view(), name="releases")]
