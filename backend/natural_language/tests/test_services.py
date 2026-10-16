"""Stub behavior and per-request configuration visibility."""

import pytest
from django.contrib.auth.models import User

from natural_language.configuration import update_configuration
from natural_language.models import AIConfiguration
from natural_language.services import QueryDisabledError, answer_question

pytestmark = pytest.mark.django_db


def test_unconfigured_feature_is_disabled(config: AIConfiguration) -> None:
    with pytest.raises(QueryDisabledError):
        answer_question("hello")


def test_enabled_stub_returns_fixed_response_and_reads_current_database(
    config: AIConfiguration, admin_user: User
) -> None:
    update_configuration(
        {"provider": "vendor", "model_name": "model", "api_key": "key", "enabled": True}, admin_user
    )
    first = answer_question("hello")
    assert first.question == "hello"
    assert first.is_stub
    assert "No broadband data was queried" in first.answer
    update_configuration({"clear_api_key": True}, admin_user)
    with pytest.raises(QueryDisabledError):
        answer_question("hello")
