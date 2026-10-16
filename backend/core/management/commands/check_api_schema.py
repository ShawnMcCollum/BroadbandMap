"""Validate and compare the generated production OpenAPI document."""

import difflib
import json
import tempfile
from pathlib import Path
from typing import Any

from django.core.management import BaseCommand, CommandError, call_command

BASELINE_PATH = Path(__file__).resolve().parents[2] / "api" / "openapi.json"


def canonical(document: Any) -> str:
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


class Command(BaseCommand):
    help = "Validate the generated production API schema and compare its reviewed baseline."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--update", action="store_true", help="Write the validated schema baseline."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        with tempfile.TemporaryDirectory(prefix="broadbandmap-openapi-") as temporary_directory:
            generated_path = Path(temporary_directory) / "openapi.json"
            try:
                call_command(
                    "spectacular",
                    urlconf="config.urls",
                    file=str(generated_path),
                    format="openapi-json",
                    validate=True,
                    fail_on_warn=True,
                    verbosity=0,
                )
            except Exception as exc:
                raise CommandError(f"OpenAPI generation or validation failed: {exc}") from exc
            try:
                document = json.loads(generated_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise CommandError(f"Could not read generated OpenAPI JSON: {exc}") from exc
            generated = canonical(document)

        if options["update"]:
            try:
                BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
                BASELINE_PATH.write_text(generated, encoding="utf-8")
            except OSError as exc:
                raise CommandError(f"Could not update OpenAPI baseline: {exc}") from exc
            self.stdout.write(self.style.SUCCESS(f"Updated {BASELINE_PATH}"))
            return

        try:
            existing_document = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise CommandError(
                f"OpenAPI baseline is missing: {BASELINE_PATH}. Run with --update intentionally."
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Could not read OpenAPI baseline: {exc}") from exc

        existing = canonical(existing_document)
        if existing != generated:
            diff = "".join(
                difflib.unified_diff(
                    existing.splitlines(keepends=True),
                    generated.splitlines(keepends=True),
                    fromfile=str(BASELINE_PATH),
                    tofile="generated OpenAPI schema",
                )
            )
            raise CommandError(f"OpenAPI schema differs from its reviewed baseline:\n{diff}")
        self.stdout.write(self.style.SUCCESS("OpenAPI schema matches the reviewed baseline."))
