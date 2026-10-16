"""Shared API foundation test clients and identity fixtures."""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.tests.api.helpers import LOGIN_VALUE


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def csrf_client() -> APIClient:
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def ordinary_user(db: None) -> User:
    return User.objects.create_user(username="ordinary", password=LOGIN_VALUE)


@pytest.fixture
def staff_user(db: None) -> User:
    return User.objects.create_user(
        username="staff", password=LOGIN_VALUE, is_staff=True, is_active=True
    )


@pytest.fixture
def superuser(db: None) -> User:
    return User.objects.create_superuser(
        username="root", email="root@example.invalid", password=LOGIN_VALUE
    )
