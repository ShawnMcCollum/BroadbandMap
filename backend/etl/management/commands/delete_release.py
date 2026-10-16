"""Delete one release, or one state of a release, with its statuses and rollups."""

import time
from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bdc.generations import advance_generation
from bdc.models import Release
from bdc.release_options import add_release_options, find_release
from core.maintenance import vacuum_analyze
from core.write_lock import WriteLockHeld, take_write_lock
from geography.models import State
from scripts.fetch_boundaries import fips_code
from served_unserved.models import Rollup, ServedStatus
from served_unserved.release_states import delete_state, states_in_release


def not_held(release: Release, state_fips: str, states: list[State]) -> str:
    """Why the release cannot lose a state it does not hold, with the states it holds."""
    name = State.objects.filter(pk=state_fips).values_list("name", flat=True).first()
    message = f"{name or f'state {state_fips}'} is not loaded in {release}"
    if states:
        held = ", ".join(f"--state {state.geoid} ({state.name})" for state in states)
        message += f"; states it holds: {held}"
    return message


class Command(BaseCommand):
    help = (
        "Delete the release that --as-of and --processed-on name, with the statuses and rollups "
        "of every state in it, in one transaction. With --state, delete only that state's "
        "statuses and rollups in the release, and the release with its last state. Other "
        "releases and states are not changed. Once the deletion has committed, the tables it "
        "changed are vacuumed and analyzed. Stops at once if another data load, deletion or "
        "rollup rebuild is running."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        add_release_options(parser, required=True)
        parser.add_argument(
            "--state",
            type=fips_code,
            metavar="FIPS",
            help=(
                "two-digit FIPS code of the one state to delete from the release, e.g. 54; "
                "deleting the release's last state deletes the release"
            ),
        )
        parser.add_argument(
            "--noinput",
            "--no-input",
            action="store_false",
            dest="interactive",
            help="delete without asking for confirmation",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        release = find_release(options["as_of"], options["processed_on"])
        if options["state"] is None:
            self.remove_release(release, interactive=options["interactive"])
        else:
            self.remove_state(release, options["state"], interactive=options["interactive"])

    def confirm(self, question: str) -> bool:
        """Ask the question and return whether the answer is 'yes'; say so when it is not."""
        try:
            answer = input(f"{question} Type 'yes' to continue, or 'no' to cancel: ")
        except EOFError:
            raise CommandError(
                "no answer to the confirmation question; use --no-input to delete without asking"
            ) from None
        if answer != "yes":
            self.stdout.write("Deletion cancelled.")
            return False
        return True

    def remove_release(self, release: Release, *, interactive: bool) -> None:
        """Delete the release, with the statuses and rollups of every state in it."""
        if interactive and not self.confirm(f"Delete {release}, with its statuses and rollups?"):
            return

        began = time.monotonic()
        # By its dates, not its id: a deletion and a reload while the question was open give the
        # release a new id (ADR 0013, decision 4).
        try:
            with transaction.atomic(durable=True):
                # After the answer, so that no lock is held while waiting for one.
                take_write_lock(f"deletion of {release}")
                _, deleted = Release.objects.filter(
                    as_of=release.as_of, processed_on=release.processed_on
                ).delete()
        except WriteLockHeld as error:
            raise CommandError(str(error)) from error
        if not deleted.get(Release._meta.label):
            raise CommandError(f"{release} is no longer loaded")
        statuses = deleted.get(ServedStatus._meta.label, 0)
        rollups = deleted.get(Rollup._meta.label, 0)
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {release}: {statuses:,} statuses and {rollups:,} rollups "
                f"in {time.monotonic() - began:.0f} s."
            )
        )
        vacuum_analyze((ServedStatus, Rollup, Release), self.stdout.write)

    def remove_state(self, release: Release, state_fips: str, *, interactive: bool) -> None:
        """Delete the state's statuses and rollups in the release, and the release with its last
        state."""
        states = states_in_release(release)
        state = next((state for state in states if state.geoid == state_fips), None)
        if state is None:
            raise CommandError(not_held(release, state_fips, states))
        # Whether the question says the release goes too; checked again under the lock.
        warned = len(states) == 1
        question = f"Delete {state.name} from {release}, with its statuses and rollups there?"
        if warned:
            question += " It is the release's only state, so the release is deleted too."
        if interactive and not self.confirm(question):
            return

        began = time.monotonic()
        try:
            with transaction.atomic(durable=True):
                # After the answer, so that no lock is held while waiting for one.
                take_write_lock(f"deletion of state {state_fips} from {release}")
                # Read again under the lock: another writer may have run while the question was
                # open. By its dates, as remove_release does.
                current = Release.objects.filter(
                    as_of=release.as_of, processed_on=release.processed_on
                ).first()
                if current is None:
                    raise CommandError(f"{release} is no longer loaded")
                held = [other.geoid for other in states_in_release(current)]
                if state_fips not in held:
                    raise CommandError(f"{state.name} is no longer loaded in {release}")
                # Decided before deleting: once the state's statuses are deleted, finding whether
                # the release has any left reads past every deleted row's index entry.
                last = held == [state_fips]
                if last and interactive and not warned:
                    # The answer did not cover deleting the release. Asking again here would
                    # hold the write lock while waiting for the answer.
                    raise CommandError(
                        f"{state.name} became the only state of {release} while the question "
                        "was open, so nothing was deleted; run the command again to delete it "
                        "with the release"
                    )
                if last:
                    _, deleted = Release.objects.filter(pk=current.pk).delete()
                    statuses = deleted.get(ServedStatus._meta.label, 0)
                    rollups = deleted.get(Rollup._meta.label, 0)
                else:
                    statuses, rollups = delete_state(current, state_fips)
                    advance_generation(current)
        except WriteLockHeld as error:
            raise CommandError(str(error)) from error

        message = (
            f"Deleted {state.name} from {release}: {statuses:,} statuses and {rollups:,} rollups "
            f"in {time.monotonic() - began:.0f} s."
        )
        if last:
            message += " It was the release's only state, so the release was deleted too."
        self.stdout.write(self.style.SUCCESS(message))
        changed = (ServedStatus, Rollup, Release) if last else (ServedStatus, Rollup)
        vacuum_analyze(changed, self.stdout.write)
