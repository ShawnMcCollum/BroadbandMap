"""Explicit public and administrator access policy tests."""

import pytest
from django.contrib.auth.models import Permission, User
from rest_framework.test import APIClient

from core.tests.api.helpers import LOGIN_VALUE, problem

pytestmark = pytest.mark.urls("core.tests.api.urls")


@pytest.mark.parametrize("method", ["get", "head", "options"])
def test_public_read_methods_are_anonymous_and_bounded(api_client: APIClient, method: str) -> None:
    response = getattr(api_client, method)("/api/v1/public/")
    assert response.status_code == 200
    if method == "get":
        assert response.json() == {"id": "00123", "count": 4, "enabled": True}
    if method == "head":
        assert response.content == b""


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
@pytest.mark.parametrize("identity", ["anonymous", "staff"])
def test_public_read_rejects_writes_for_every_identity(
    api_client: APIClient, staff_user: User, method: str, identity: str
) -> None:
    if identity == "staff":
        api_client.force_login(staff_user)
    response = getattr(api_client, method)("/api/v1/public/", data={})
    assert response.status_code == 405
    body = problem(response)
    assert body["code"] == "method_not_allowed"
    assert set(response["Allow"].split(", ")) == {"GET", "HEAD", "OPTIONS"}


@pytest.mark.parametrize("identity", ["anonymous", "ordinary", "staff", "superuser"])
def test_unmarked_view_denies_all_callers(
    api_client: APIClient,
    ordinary_user: User,
    staff_user: User,
    superuser: User,
    identity: str,
) -> None:
    user = {"ordinary": ordinary_user, "staff": staff_user, "superuser": superuser}.get(identity)
    if user:
        api_client.force_login(user)
    response = api_client.get("/api/v1/unmarked/")
    assert response.status_code == 403
    expected_code = "not_authenticated" if identity == "anonymous" else "permission_denied"
    assert problem(response)["code"] == expected_code


def _grant_operation_permission(user: User) -> None:
    permission = Permission.objects.get(content_type__app_label="bdc", codename="view_release")
    user.user_permissions.add(permission)


def test_operation_permission_requires_active_staff_and_specific_permission(
    api_client: APIClient, staff_user: User, ordinary_user: User, db: None
) -> None:
    assert api_client.get("/api/v1/operation/").status_code == 403
    _grant_operation_permission(ordinary_user)
    api_client.force_login(ordinary_user)
    assert api_client.get("/api/v1/operation/").status_code == 403
    staff_user.is_active = False
    staff_user.save(update_fields=["is_active"])
    _grant_operation_permission(staff_user)
    api_client.force_login(staff_user)
    assert api_client.get("/api/v1/operation/").status_code == 403
    staff_user.is_active = True
    staff_user.save(update_fields=["is_active"])
    staff_user.user_permissions.clear()
    api_client.force_login(staff_user)
    assert api_client.get("/api/v1/operation/").status_code == 403
    _grant_operation_permission(staff_user)
    api_client.force_login(staff_user)
    response = api_client.get("/api/v1/operation/")
    assert response.status_code == 200
    assert response.json() == {"allowed": True}


def test_superuser_follows_django_has_perms_semantics(
    api_client: APIClient, superuser: User
) -> None:
    api_client.force_login(superuser)
    response = api_client.get("/api/v1/operation/")
    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/api/v1/operation-missing/", "/api/v1/operation-empty/"])
def test_operation_permission_fails_closed_without_declaration(
    api_client: APIClient, staff_user: User, path: str
) -> None:
    api_client.force_login(staff_user)
    assert api_client.get(path).status_code == 403


def test_session_csrf_is_enforced_for_unsafe_operation(
    csrf_client: APIClient, staff_user: User
) -> None:
    _grant_operation_permission(staff_user)
    assert csrf_client.login(username="staff", password=LOGIN_VALUE)
    no_token = csrf_client.post("/api/v1/operation/", data={}, format="json")
    assert no_token.status_code == 403
    csrf_client.get("/api/v1/csrf-token/")
    cookie_token = csrf_client.cookies["csrftoken"].value
    wrong = csrf_client.post(
        "/api/v1/operation/", data={}, format="json", HTTP_X_CSRFTOKEN="0" * 64
    )
    assert wrong.status_code == 403
    accepted = csrf_client.post(
        "/api/v1/operation/",
        data={},
        format="json",
        HTTP_X_CSRFTOKEN=csrf_client.cookies["csrftoken"].value,
    )
    assert accepted.status_code == 200
    assert accepted.json() == {"saved": True}
    assert cookie_token


def test_authenticated_nonstaff_remains_denied_with_valid_csrf(
    csrf_client: APIClient, ordinary_user: User
) -> None:
    _grant_operation_permission(ordinary_user)
    assert csrf_client.login(username="ordinary", password=LOGIN_VALUE)
    csrf_client.get("/api/v1/csrf-token/")
    response = csrf_client.post(
        "/api/v1/operation/",
        data={},
        format="json",
        HTTP_X_CSRFTOKEN=csrf_client.cookies["csrftoken"].value,
    )
    assert response.status_code == 403
