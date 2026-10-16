"""Locked updates and sanitized representations for installation settings."""

import re
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from rest_framework import serializers

from natural_language.credentials import (
    credential_is_available,
    encrypt_credential,
    require_credential,
)
from natural_language.models import AIConfiguration

PROVIDER_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")


def get_configuration() -> AIConfiguration:
    return AIConfiguration.objects.get(pk=1)


def configuration_payload(config: AIConfiguration) -> dict[str, Any]:
    return {
        "enabled": config.enabled,
        "provider": config.provider,
        "model_name": config.model_name,
        "timeout_seconds": config.timeout_seconds,
        "max_output_tokens": config.max_output_tokens,
        "key_configured": bool(config.api_key_ciphertext),
        "key_available": credential_is_available(config.api_key_ciphertext),
        "is_stub": True,
        "provider_validated": False,
        "updated_at": config.updated_at.isoformat(),
    }


def effective_enabled(config: AIConfiguration) -> bool:
    return bool(
        config.enabled
        and config.provider
        and config.model_name.strip()
        and config.api_key_ciphertext
        and credential_is_available(config.api_key_ciphertext)
    )


def _raise(field: str, message: str, code: str = "invalid") -> None:
    raise serializers.ValidationError({field: [serializers.ErrorDetail(message, code=code)]})


def update_configuration(changes: dict[str, Any], user: AbstractBaseUser) -> AIConfiguration:
    with transaction.atomic():
        config = AIConfiguration.objects.select_for_update().get(pk=1)
        original_provider = config.provider
        original_ciphertext = config.api_key_ciphertext
        for field in ("provider", "model_name", "timeout_seconds", "max_output_tokens"):
            if field in changes:
                setattr(config, field, changes[field])
        if changes.get("clear_api_key", False):
            if "api_key" in changes or changes.get("enabled") is True:
                _raise("clear_api_key", "Cannot combine clearing with a key or enabling.")
            config.api_key_ciphertext = ""
            config.enabled = False
        else:
            if "enabled" in changes:
                config.enabled = changes["enabled"]
            if "api_key" in changes:
                config.api_key_ciphertext = encrypt_credential(
                    changes["api_key"], ciphertext_exists=bool(original_ciphertext)
                )
            elif (
                original_ciphertext
                and "provider" in changes
                and changes["provider"] != original_provider
            ):
                _raise("api_key", "Replace or explicitly clear the key when changing provider.")

            if config.api_key_ciphertext and config.enabled and changes.get("enabled") is not False:
                require_credential(config.api_key_ciphertext)

        if config.provider and not PROVIDER_PATTERN.fullmatch(config.provider):
            _raise("provider", "Use a lowercase provider identifier.")
        if len(config.model_name) > 200 or (config.enabled and not config.model_name.strip()):
            _raise("model_name", "Enter a model name of at most 200 characters.")
        if config.enabled and (not config.provider or not config.api_key_ciphertext):
            _raise("enabled", "Provider, model name, and a credential are required to enable AI.")

        config.updated_by_id = user.pk
        config.save()
        return config
