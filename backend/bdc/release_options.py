"""Command-line options that name one release by its two dates (ADR 0013, decision 4)."""

from argparse import ArgumentParser, ArgumentTypeError
from datetime import date
from typing import Any

from django.core.management.base import CommandError

from bdc.models import Release


def iso_date(value: str) -> date:
    """A date given as YYYY-MM-DD, for argparse."""
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ArgumentTypeError(f"{value!r} is not a date in the form YYYY-MM-DD") from None


def add_release_options(parser: ArgumentParser, *, required: bool) -> None:
    """Add --as-of and --processed-on, which together name one release."""
    parser.add_argument(
        "--as-of",
        type=iso_date,
        required=required,
        metavar="YYYY-MM-DD",
        help="date the release's data describes, e.g. 2025-06-30",
    )
    parser.add_argument(
        "--processed-on",
        type=iso_date,
        required=required,
        metavar="YYYY-MM-DD",
        help="date the FCC processed the release, e.g. 2026-10-01",
    )


def find_release(as_of: date, processed_on: date) -> Release:
    """The loaded release with these dates.

    Raises CommandError if none is loaded. The error lists the loaded releases by the options
    that name them.
    """
    release = Release.objects.filter(as_of=as_of, processed_on=processed_on).first()
    if release is not None:
        return release
    message = f"no release is loaded as of {as_of}, processed {processed_on}"
    loaded = [
        f"--as-of {other.as_of} --processed-on {other.processed_on}"
        for other in Release.objects.all()
    ]
    if loaded:
        message += f"; loaded releases: {', '.join(loaded)}"
    raise CommandError(message)


def release_from_options(options: dict[str, Any]) -> Release | None:
    """The release that --as-of and --processed-on name, or None when neither is given.

    Raises CommandError when only one of them is given, or when no such release is loaded.
    """
    as_of: date | None = options["as_of"]
    processed_on: date | None = options["processed_on"]
    if as_of is None and processed_on is None:
        return None
    if as_of is None or processed_on is None:
        raise CommandError("--as-of and --processed-on name a release together; give both")
    return find_release(as_of, processed_on)
