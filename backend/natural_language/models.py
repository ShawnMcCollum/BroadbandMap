"""Persistent installation-wide AI settings; credential material is never exposed."""

from django.conf import settings
from django.db import models


class AIConfiguration(models.Model):
    id = models.PositiveSmallIntegerField(
        primary_key=True,
        default=1,
        editable=False,
        help_text="Installation-wide AI configuration; identifier must be 1.",
    )
    enabled = models.BooleanField(
        default=False, help_text="Enable the configured natural-language stub."
    )
    provider = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Unverified provider identifier reserved for future integration.",
    )
    model_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Unverified model identifier supplied by the administrator.",
    )
    api_key_ciphertext = models.TextField(
        blank=True,
        default="",
        editable=False,
        help_text="Encrypted provider credential; never serialize or log.",
    )
    timeout_seconds = models.PositiveSmallIntegerField(
        default=30, help_text="Future provider timeout in seconds (1 through 120)."
    )
    max_output_tokens = models.PositiveIntegerField(
        default=1024, help_text="Future provider output limit in tokens (1 through 8192)."
    )
    updated_at = models.DateTimeField(
        auto_now=True, help_text="Time of the last successful configuration change."
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        editable=False,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Administrator who last changed the configuration.",
    )

    class Meta:
        default_permissions = ()
        permissions = [("manage_ai_configuration", "Can manage AI configuration")]
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name="nl_ai_config_singleton"),
            models.CheckConstraint(
                condition=models.Q(timeout_seconds__gte=1, timeout_seconds__lte=120),
                name="nl_ai_config_timeout_range",
            ),
            models.CheckConstraint(
                condition=models.Q(max_output_tokens__gte=1, max_output_tokens__lte=8192),
                name="nl_ai_config_output_range",
            ),
            models.CheckConstraint(
                condition=models.Q(provider="")
                | models.Q(provider__regex=r"^[a-z][a-z0-9_.-]{0,63}$"),
                name="nl_ai_config_provider_format",
            ),
            models.CheckConstraint(
                condition=models.Q(enabled=False)
                | (
                    ~models.Q(provider="")
                    & ~models.Q(model_name="")
                    & ~models.Q(api_key_ciphertext="")
                ),
                name="nl_ai_config_enabled_complete",
            ),
        ]

    def __str__(self) -> str:
        return "AI configuration (installation-wide)"
