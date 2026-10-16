"""Verify and profile first/deep location pages against the full Ohio source.

Run with pytest -m full_data -s served_unserved/tests/test_locations_full_data.py.
Only the isolated test database is loaded. No latency threshold depends on the host.
"""

import csv
import io
import json
import time
import zipfile
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from django.core import signing
from django.db import connection, transaction
from django.db.models import F
from django.test.utils import CaptureQueriesContext
from pytest_django.plugin import DjangoDbBlocker
from rest_framework.test import APIClient

from bdc.models import Release
from etl.files import DEFAULT_DATA_DIR
from etl.load import load_served_unserved
from etl.tests.helpers import clear_tables
from served_unserved.api.cursors import SALT
from served_unserved.models import Rollup
from served_unserved.queries import location_order, location_rows

FCC = DEFAULT_DATA_DIR / "bdc_39_fixed_broadband_served_unserved_D25_29sep2026.zip"
URL = "/api/v1/served-unserved/locations/"
SOURCE_FLAGS = {
    "any_100_20": "any_dl100_ul20",
    "wired_100_20": "wired_dl100_ul20",
    "terrestrial_100_20": "terrestrial_dl100_ul20",
}
pytestmark = [
    pytest.mark.full_data,
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(not FCC.exists(), reason="Ohio December source is not available"),
]


@pytest.fixture(scope="module")
def ohio(django_db_setup: None, django_db_blocker: DjangoDbBlocker) -> Iterator[None]:
    with django_db_blocker.unblock():
        load_served_unserved(DEFAULT_DATA_DIR, progress=print, fcc_file=FCC)
    yield
    with django_db_blocker.unblock(), transaction.atomic():
        clear_tables()


def plan_nodes(plan: dict[str, Any]) -> list[str]:
    result = [plan["Node Type"] + (" " + plan["Index Name"] if "Index Name" in plan else "")]
    for child in plan.get("Plans", []):
        result.extend(plan_nodes(child))
    return result


@pytest.mark.usefixtures("ohio")
def test_first_deep_and_filtered_pages_match_raw_source() -> None:
    release = Release.objects.get()
    county = Rollup.objects.filter(release=release, level="county").order_by("-locations").first()
    assert county is not None
    # Independent CSV reader establishes county membership, order and flags.
    expected = []
    with zipfile.ZipFile(FCC) as archive, archive.open(FCC.stem + ".csv") as raw:
        for row in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig")):
            if row["block_geoid"].startswith(county.code):
                expected.append(row)
    expected.sort(key=lambda row: int(row["location_id"]))
    assert len(expected) == county.locations
    assert len(expected) > 100_000
    cutoff = int(expected[len(expected) * 9 // 10]["location_id"])
    client = APIClient()
    records = []
    for flag in ("any", "wired", "terrestrial"):
        for status in (None, "served", "not_served"):
            params: dict[str, Any] = {
                "level": "county",
                "code": county.code,
                "page_size": 100,
                "flag": flag,
            }
            if status is not None:
                params["status"] = status
            source = [
                row
                for row in expected
                if status is None
                or (row[SOURCE_FLAGS[flag + "_100_20"]] == "1") == (status == "served")
            ]
            started = time.monotonic()
            first_response = client.get(URL, params)
            first_ms = (time.monotonic() - started) * 1000
            assert first_response.status_code == 200
            first = first_response.json()
            assert [row["location_id"] for row in first["results"]] == [
                row["location_id"] for row in source[:100]
            ]
            if first["next"] is None:
                continue
            query = parse_qs(urlsplit(first["next"]).query)
            payload = signing.loads(query["cursor"][0], salt=SALT)
            query["cursor"] = [
                signing.dumps({**payload, "position": cutoff}, salt=SALT, compress=True)
            ]
            with CaptureQueriesContext(connection) as queries:
                started = time.monotonic()
                deep_response = client.get(URL + "?" + urlencode(query, doseq=True))
                deep_ms = (time.monotonic() - started) * 1000
            assert deep_response.status_code == 200
            deep = deep_response.json()
            deep_source = [row for row in source if int(row["location_id"]) > cutoff][:100]
            assert [row["location_id"] for row in deep["results"]] == [
                row["location_id"] for row in deep_source
            ]
            for actual, raw_row in zip(deep["results"], deep_source, strict=True):
                assert actual["block_geoid"] == raw_row["block_geoid"]
                assert actual["h3_res8"] == raw_row["h3_res8_id"]
                for name in ("any_100_20", "wired_100_20", "terrestrial_100_20"):
                    assert actual[name] == (raw_row[SOURCE_FLAGS[name]] == "1")
            assert not any(
                "COUNT(" in q["sql"].upper() or "OFFSET" in q["sql"].upper() for q in queries
            )
            rows = location_rows(release, params).filter(location_id__gt=cutoff)
            if status is not None:
                rows = rows.filter(**{flag + "_100_20": status == "served"})
            plan = json.loads(
                rows.order_by(location_order())
                .values(
                    "location_id",
                    "h3_res8",
                    "any_100_20",
                    "wired_100_20",
                    "terrestrial_100_20",
                    block_geoid=F("block_id"),
                )[:101]
                .explain(analyze=True, buffers=True, format="json")
            )[0]
            records.append(
                {
                    "flag": flag,
                    "status": status,
                    "first_http_ms": round(first_ms, 1),
                    "deep_http_ms": round(deep_ms, 1),
                    "deep_sql_ms": plan["Execution Time"],
                    "nodes": plan_nodes(plan["Plan"]),
                    "queries": len(queries),
                }
            )
    print(
        json.dumps(
            {
                "county": county.code,
                "locations": len(expected),
                "cutoff": cutoff,
                "profiles": records,
            }
        )
    )

    # First/deep query plans at every geography level, not just the largest county.
    for level in ("tract", "block_group", "block", "h3_res8", "place", "county_subdivision"):
        area = Rollup.objects.filter(release=release, level=level).order_by("-locations").first()
        assert area is not None
        params = {"level": level, "code": area.code, "page_size": 100}
        response = client.get(URL, params)
        assert response.status_code == 200
        rows = location_rows(release, params)
        count = rows.count()
        anchor = rows.order_by("location_id").values_list("location_id", flat=True)[count * 9 // 10]
        for position in (None, anchor):
            selected = rows if position is None else rows.filter(location_id__gt=position)
            plan = json.loads(
                selected.order_by(location_order())
                .values(
                    "location_id",
                    "block_id",
                    "h3_res8",
                    "any_100_20",
                    "wired_100_20",
                    "terrestrial_100_20",
                )[:101]
                .explain(analyze=True, buffers=True, format="json")
            )[0]
            print(
                json.dumps(
                    {
                        "level": level,
                        "code": area.code,
                        "locations": count,
                        "deep": position is not None,
                        "sql_ms": plan["Execution Time"],
                        "nodes": plan_nodes(plan["Plan"]),
                    }
                )
            )
