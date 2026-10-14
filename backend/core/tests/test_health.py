from collections.abc import Iterator
from unittest.mock import patch

import pytest
from django.test import Client

COMPONENTS = ("database", "redis", "worker")


@pytest.fixture
def all_up() -> Iterator[None]:
    with (
        patch("core.views.check_database", return_value=True),
        patch("core.views.check_redis", return_value=True),
        patch("core.views.check_worker", return_value=True),
    ):
        yield


@pytest.mark.usefixtures("all_up")
def test_health_reports_ok_when_everything_is_up(client: Client) -> None:
    response = client.get("/api/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "redis": "ok", "worker": "ok"}


@pytest.mark.usefixtures("all_up")
@pytest.mark.parametrize("component", COMPONENTS)
def test_health_names_the_unreachable_component(client: Client, component: str) -> None:
    with patch(f"core.views.check_{component}", return_value=False):
        response = client.get("/api/health/")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    for name in COMPONENTS:
        assert body[name] == ("unreachable" if name == component else "ok")


@pytest.mark.django_db
def test_database_check_reaches_postgis() -> None:
    from core.views import check_database

    assert check_database() is True


def test_health_rejects_post(client: Client) -> None:
    response = client.post("/api/health/")

    assert response.status_code == 405
