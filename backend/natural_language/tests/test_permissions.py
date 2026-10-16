"""Administrator operation permission matrix for configuration endpoints."""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.tests.api.helpers import LOGIN_VALUE, problem

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "identity", ["anonymous", "ordinary", "inactive", "staff", "permitted", "superuser"]
)
def test_only_permitted_active_staff_can_read_configuration(
    api_client: APIClient, admin_user: User, identity: str
) -> None:
    if identity == "ordinary":
        user = User.objects.create_user("ordinary", password=LOGIN_VALUE)
        user.user_permissions.add(*admin_user.user_permissions.all())
    elif identity == "inactive":
        user = admin_user
        user.is_active = False
        user.save(update_fields=["is_active"])
    elif identity == "staff":
        user = User.objects.create_user("staff-no-perm", password=LOGIN_VALUE, is_staff=True)
    elif identity == "superuser":
        user = User.objects.create_superuser("root", "root@example.invalid", LOGIN_VALUE)
    elif identity == "permitted":
        user = admin_user
    else:
        user = None
    if user is not None:
        api_client.force_login(user)
    response = api_client.get("/api/v1/natural-language/configuration/")
    if identity in {"anonymous", "ordinary", "inactive", "staff"}:
        assert response.status_code == 403
        assert problem(response)["code"] in {"not_authenticated", "permission_denied"}
    else:
        assert response.status_code == 200


def test_authorized_configuration_methods_and_options(configuration: APIClient) -> None:
    assert configuration.options("/api/v1/natural-language/configuration/").status_code == 200
    response = configuration.post("/api/v1/natural-language/configuration/", {}, format="json")
    assert response.status_code == 405
    assert set(response["Allow"].split(", ")) == {"GET", "HEAD", "OPTIONS", "PATCH"}


@pytest.mark.parametrize("identity", ["anonymous", "ordinary", "inactive", "staff"])
def test_unauthorized_identities_cannot_patch_configuration(
    api_client: APIClient, admin_user: User, identity: str
) -> None:
    if identity == "ordinary":
        user = User.objects.create_user("ordinary-patch", password=LOGIN_VALUE)
    elif identity == "inactive":
        user = admin_user
        user.is_active = False
        user.save(update_fields=["is_active"])
    elif identity == "staff":
        user = User.objects.create_user("staff-patch", password=LOGIN_VALUE, is_staff=True)
    else:
        user = None
    if user is not None:
        api_client.force_login(user)
    response = api_client.patch(
        "/api/v1/natural-language/configuration/", {"enabled": False}, format="json"
    )
    assert response.status_code == 403
    assert problem(response)["code"] in {"not_authenticated", "permission_denied"}


def test_configuration_head_and_options_enforce_access(configuration: APIClient) -> None:
    path = "/api/v1/natural-language/configuration/"
    head = configuration.head(path)
    assert head.status_code == 200 and head.content == b""
    assert APIClient().options(path).status_code == 403
    public_head = APIClient().head("/api/v1/natural-language/")
    assert public_head.status_code == 200 and public_head.content == b""
    assert APIClient().options("/api/v1/natural-language/query/").status_code == 200
