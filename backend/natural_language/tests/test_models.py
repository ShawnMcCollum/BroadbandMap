"""Database-level singleton and check constraint behavior."""

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction

from natural_language.models import AIConfiguration

pytestmark = pytest.mark.django_db


def test_migration_seeds_disabled_singleton(config: AIConfiguration) -> None:
    assert AIConfiguration.objects.count() == 1
    assert config.pk == 1
    assert config.enabled is False


@pytest.mark.parametrize(
    "changes",
    [
        {"id": 2},
        {"timeout_seconds": 0},
        {"timeout_seconds": 121},
        {"max_output_tokens": 0},
        {"max_output_tokens": 8193},
        {"provider": "Bad Provider"},
        {"enabled": True},
    ],
)
def test_database_constraints_reject_invalid_state(
    config: AIConfiguration, changes: dict[str, object]
) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        AIConfiguration.objects.filter(pk=1).update(**changes)


def test_updater_deletion_preserves_configuration(
    config: AIConfiguration, admin_user: User
) -> None:
    config.updated_by = admin_user
    config.save()
    admin_user.delete()
    config.refresh_from_db()
    assert config.pk == 1
    assert config.updated_by is None
