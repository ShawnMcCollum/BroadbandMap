"""Real writers invalidate cursors atomically, while readers retain their snapshots."""

import json
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from django.db import close_old_connections, connection
from openapi_schema_validator import OAS30Validator
from rest_framework.test import APIClient

from bdc.api.queries import release_metadata
from bdc.generations import advance_generation
from bdc.models import Release
from core.management.commands.check_api_schema import BASELINE_PATH
from core.tests.api.helpers import problem
from etl import load as loader
from etl.load import load_served_unserved
from etl.management.commands import delete_release
from etl.tests.helpers import WV_STEM, j25_csv, make_data_dir, wv_csv
from served_unserved.api import views
from served_unserved.management.commands import build_rollups
from served_unserved.models import ServedStatus

pytestmark = pytest.mark.django_db(transaction=True)
URL = "/api/v1/served-unserved/locations/"
PARAMS: dict[str, Any] = {"level": "county", "code": "39055", "page_size": 5}
DATES = ["--as-of", "2025-12-31", "--processed-on", "2026-09-29"]


@pytest.fixture
def loaded_data(tmp_path: Path) -> Path:
    data = make_data_dir(tmp_path)
    load_served_unserved(data)
    return data


def write(operation: str, data: Path) -> None:
    if operation == "replace":
        load_served_unserved(data, replace=True)
    elif operation == "add_state":
        wv = make_data_dir(data.parent / "wv", csv=wv_csv(), fcc_stem=WV_STEM)
        load_served_unserved(wv)
    elif operation == "delete_state":
        call_command("delete_release", *DATES, "--state", "54", "--no-input", stdout=StringIO())
    elif operation in {"delete", "recreate"}:
        call_command("delete_release", *DATES, "--no-input", stdout=StringIO())
        if operation == "recreate":
            load_served_unserved(data)
    else:
        assert operation == "rebuild"
        call_command("build_rollups", *DATES, stdout=StringIO())


@pytest.mark.parametrize(
    "operation", ["replace", "add_state", "delete_state", "delete", "recreate", "rebuild"]
)
def test_committed_writers_require_restart(loaded_data: Path, operation: str) -> None:
    if operation == "delete_state":
        write("add_state", loaded_data)
    release = Release.objects.get()
    identity, generation = release.pk, release.data_generation
    client = APIClient()
    first = client.get(URL, PARAMS).json()
    write(operation, loaded_data)
    stale = client.get(first["next"])
    assert stale.status_code == 409
    assert problem(stale)["code"] == "dataset_changed"
    assert "Restart" in stale.json()["detail"]
    document = json.loads(BASELINE_PATH.read_text())
    schema = document["paths"][URL]["get"]["responses"]["409"]["content"][
        "application/problem+json"
    ]["schema"]
    OAS30Validator(document).evolve(schema=schema).validate(stale.json())
    fresh = client.get(URL, PARAMS)
    assert fresh.status_code == (404 if operation == "delete" else 200)
    if operation not in {"delete", "recreate"}:
        release.refresh_from_db()
        assert release.pk == identity
        assert release.data_generation == generation + 1
    elif operation == "recreate":
        assert Release.objects.get().pk != identity


def test_failed_replacement_rolls_back_data_and_generation(
    loaded_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = Release.objects.get()
    first = APIClient().get(URL, PARAMS).json()
    # Change the source so rollback must restore actual rows as well as the token.
    make_data_dir(loaded_data.parent, csv=j25_csv())

    def fail_after_generation(current: Release) -> None:
        advance_generation(current)
        raise RuntimeError("failure before commit")

    monkeypatch.setattr(loader, "advance_generation", fail_after_generation)
    with pytest.raises(RuntimeError, match="before commit"):
        load_served_unserved(loaded_data, replace=True)
    current = Release.objects.get()
    assert current.data_generation == release.data_generation
    assert ServedStatus.objects.filter(release=current).count() == 31
    assert APIClient().get(first["next"]).status_code == 200


@pytest.mark.parametrize("operation", ["rebuild", "delete_state"])
def test_failed_command_preserves_generation_and_traversal(
    loaded_data: Path, operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    write("add_state", loaded_data)
    release = Release.objects.get()
    first = APIClient().get(URL, PARAMS).json()

    def fail_after_generation(current: Release) -> None:
        advance_generation(current)
        raise RuntimeError("failure before commit")

    module = build_rollups if operation == "rebuild" else delete_release
    monkeypatch.setattr(module, "advance_generation", fail_after_generation)
    with pytest.raises(RuntimeError, match="before commit"):
        write(operation, loaded_data)
    assert Release.objects.get().data_generation == release.data_generation
    assert ServedStatus.objects.filter(release=release).count() == 37
    assert APIClient().get(first["next"]).status_code == 200


@pytest.mark.parametrize("operation", ["replace", "add_state", "delete_state", "delete", "rebuild"])
def test_one_request_sees_old_snapshot_during_real_writer(
    loaded_data: Path, operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    if operation == "delete_state":
        write("add_state", loaded_data)
    expected = APIClient().get(URL, PARAMS).json()

    def commit_elsewhere() -> None:
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '3s'")
                cursor.execute("SET statement_timeout = '8s'")
            write(operation, loaded_data)
        finally:
            connection.close()

    def between_reads(release: Release) -> dict[str, Any]:
        metadata = release_metadata(release)
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(commit_elsewhere).result(timeout=15)
        return metadata

    monkeypatch.setattr(views, "release_metadata", between_reads)
    response = APIClient().get(URL, PARAMS)
    assert response.status_code == 200
    body = response.json()
    assert body["results"] == expected["results"]
    assert body["release"] == expected["release"]
    monkeypatch.setattr(views, "release_metadata", release_metadata)
    assert APIClient().get(body["next"]).status_code == 409
