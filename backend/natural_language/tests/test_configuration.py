"""Atomic merged updates and sanitized persisted reads."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from django.contrib.auth.models import User
from django.db import close_old_connections
from rest_framework import serializers

from natural_language.configuration import configuration_payload, update_configuration
from natural_language.credentials import CredentialStorageUnavailable, require_credential
from natural_language.models import AIConfiguration

pytestmark = pytest.mark.django_db


def test_credential_omission_preserves_value_and_response_is_sanitized(
    config: AIConfiguration, admin_user: User
) -> None:
    update_configuration(
        {"provider": "vendor", "model_name": "model-x", "api_key": "first"}, admin_user
    )
    config.refresh_from_db()
    ciphertext = config.api_key_ciphertext
    payload = configuration_payload(config)
    assert "first" not in ciphertext
    assert "first" not in repr(payload)
    assert payload["key_configured"] is True
    update_configuration({"timeout_seconds": 50}, admin_user)
    config.refresh_from_db()
    assert config.api_key_ciphertext == ciphertext
    assert require_credential(ciphertext) == "first"


def test_initial_provider_without_key_and_provider_with_clear_are_valid(
    config: AIConfiguration, admin_user: User
) -> None:
    update_configuration({"provider": "vendor"}, admin_user)
    config.refresh_from_db()
    assert config.provider == "vendor" and not config.api_key_ciphertext
    update_configuration({"model_name": "model", "api_key": "key"}, admin_user)
    update_configuration({"provider": "other", "clear_api_key": True}, admin_user)
    config.refresh_from_db()
    assert config.provider == "other"
    assert not config.enabled and not config.api_key_ciphertext


def test_provider_change_requires_replacement_or_explicit_clear(
    config: AIConfiguration, admin_user: User
) -> None:
    update_configuration({"provider": "vendor", "model_name": "x", "api_key": "key"}, admin_user)
    with pytest.raises(serializers.ValidationError):
        update_configuration({"provider": "other"}, admin_user)
    config.refresh_from_db()
    assert config.provider == "vendor"
    update_configuration({"provider": "other", "api_key": "new"}, admin_user)
    config.refresh_from_db()
    assert require_credential(config.api_key_ciphertext) == "new"


def test_clear_disables_then_allows_recovery(
    config: AIConfiguration, admin_user: User, key_file: Path
) -> None:
    update_configuration(
        {"provider": "vendor", "model_name": "x", "api_key": "key", "enabled": True}, admin_user
    )
    key_file.unlink()
    with pytest.raises(CredentialStorageUnavailable):
        update_configuration({"api_key": "replacement"}, admin_user)
    update_configuration({"clear_api_key": True}, admin_user)
    config.refresh_from_db()
    assert config.enabled is False and config.api_key_ciphertext == ""
    update_configuration({"api_key": "replacement"}, admin_user)
    config.refresh_from_db()
    assert require_credential(config.api_key_ciphertext) == "replacement"


@pytest.mark.django_db(transaction=True)
def test_concurrent_first_credential_saves_leave_decryptable_final_value(
    admin_user: User, key_file: Path
) -> None:
    # Transactional tests flush migration data; restore the installation row
    # before opening independent connections. The seed itself is checked above.
    AIConfiguration.objects.get_or_create(pk=1)
    users = [admin_user.pk, User.objects.create_user("second-admin", is_staff=True).pk]

    ready = Barrier(2)

    def save(index: int) -> str:
        close_old_connections()
        user = User.objects.get(pk=users[index])
        ready.wait(timeout=10)
        saved = update_configuration(
            {"provider": "vendor", "model_name": f"model-{index}", "api_key": f"secret-{index}"},
            user,
        )
        close_old_connections()
        return saved.api_key_ciphertext

    with ThreadPoolExecutor(max_workers=2) as pool:
        ciphertexts = list(pool.map(save, (0, 1)))
    # Both successful writes must use the same installation encryption material,
    # including the first result after a concurrent update has committed.
    assert [require_credential(value) for value in ciphertexts] == ["secret-0", "secret-1"]
    config = AIConfiguration.objects.get(pk=1)
    assert require_credential(config.api_key_ciphertext) in {"secret-0", "secret-1"}


def test_failed_database_write_preserves_previous_settings_and_key_material(
    config: AIConfiguration, admin_user: User, key_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    update_configuration({"provider": "vendor", "api_key": "original"}, admin_user)
    material = key_file.read_bytes()

    def fail_save(self: AIConfiguration) -> None:
        raise RuntimeError("Simulated database failure")

    with monkeypatch.context() as patch:
        patch.setattr(AIConfiguration, "save", fail_save)
        with pytest.raises(RuntimeError, match="Simulated database failure"):
            update_configuration({"provider": "other", "api_key": "replacement"}, admin_user)
    config.refresh_from_db()
    assert config.provider == "vendor"
    assert require_credential(config.api_key_ciphertext) == "original"
    assert key_file.read_bytes() == material
