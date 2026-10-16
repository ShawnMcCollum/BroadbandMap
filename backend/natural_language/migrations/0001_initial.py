"""Create the installation settings row and its permission boundary."""

import django.db.models.deletion
from django.apps.registry import Apps
from django.conf import settings
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor


def create_singleton(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    configuration = apps.get_model("natural_language", "AIConfiguration")
    configuration.objects.using(schema_editor.connection.alias).get_or_create(pk=1)


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="AIConfiguration",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1,
                        editable=False,
                        help_text="Installation-wide AI configuration; identifier must be 1.",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "enabled",
                    models.BooleanField(
                        default=False, help_text="Enable the configured natural-language stub."
                    ),
                ),
                (
                    "provider",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Unverified provider identifier reserved for future integration.",
                        max_length=64,
                    ),
                ),
                (
                    "model_name",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Unverified model identifier supplied by the administrator.",
                        max_length=200,
                    ),
                ),
                (
                    "api_key_ciphertext",
                    models.TextField(
                        blank=True,
                        default="",
                        editable=False,
                        help_text="Encrypted provider credential; never serialize or log.",
                    ),
                ),
                (
                    "timeout_seconds",
                    models.PositiveSmallIntegerField(
                        default=30, help_text="Future provider timeout in seconds (1 through 120)."
                    ),
                ),
                (
                    "max_output_tokens",
                    models.PositiveIntegerField(
                        default=1024,
                        help_text="Future provider output limit in tokens (1 through 8192).",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, help_text="Time of the last successful configuration change."
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        help_text="Administrator who last changed the configuration.",
                    ),
                ),
            ],
            options={
                "default_permissions": (),
                "permissions": [("manage_ai_configuration", "Can manage AI configuration")],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("id", 1)), name="nl_ai_config_singleton"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("timeout_seconds__gte", 1), ("timeout_seconds__lte", 120)
                        ),
                        name="nl_ai_config_timeout_range",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("max_output_tokens__gte", 1), ("max_output_tokens__lte", 8192)
                        ),
                        name="nl_ai_config_output_range",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("provider", ""))
                        | models.Q(("provider__regex", "^[a-z][a-z0-9_.-]{0,63}$")),
                        name="nl_ai_config_provider_format",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("enabled", False))
                        | (
                            ~models.Q(("provider", ""))
                            & ~models.Q(("model_name", ""))
                            & ~models.Q(("api_key_ciphertext", ""))
                        ),
                        name="nl_ai_config_enabled_complete",
                    ),
                ],
            },
        ),
        migrations.RunPython(create_singleton, migrations.RunPython.noop),
    ]
