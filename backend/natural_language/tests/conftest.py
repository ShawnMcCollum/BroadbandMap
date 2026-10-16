"""Isolated credential material and users for natural-language tests."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APIClient

from core.tests.api.helpers import LOGIN_VALUE
from natural_language.models import AIConfiguration


@pytest.fixture
def config(db: None) -> AIConfiguration:
    return AIConfiguration.objects.get(pk=1)


@pytest.fixture
def key_file(tmp_path: Path) -> Path:
    return tmp_path / "secret-volume" / "ai-credentials.key"


@pytest.fixture(autouse=True)
def credential_path(key_file: Path) -> Iterator[None]:
    with override_settings(AI_CREDENTIALS_KEY_FILE=key_file):
        yield


@pytest.fixture
def admin_user(db: None) -> User:
    user = User.objects.create_user("ai-admin", password=LOGIN_VALUE, is_staff=True)
    from django.contrib.auth.models import Permission

    permission = Permission.objects.get(
        content_type__app_label="natural_language", codename="manage_ai_configuration"
    )
    user.user_permissions.add(permission)
    return user


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def configuration(api_client: APIClient, admin_user: User) -> APIClient:
    api_client.force_login(admin_user)
    return api_client
