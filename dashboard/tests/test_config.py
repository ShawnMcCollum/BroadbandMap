import pytest

from api import client_for
from config import base_url, map_link


@pytest.mark.parametrize(
    "value",
    [
        "ftp://host/",
        "javascript:alert(1)",
        "http://user:pass@host/",
        "http://host/?secret=x",
        "http://host/#fragment",
        "http://host:bad/",
        "http://host\\path/",
        "http://host/\n",
        "http:///",
        "",
        " http://host/",
    ],
)
def test_invalid_destinations(value: str) -> None:
    with pytest.raises(ValueError):
        base_url(value)


def test_map_uses_public_url_same_tab_and_escaping() -> None:
    assert map_link("https://map.example:9443/app/") == (
        '<a href="https://map.example:9443/app/#/map" target="_self">Map</a>'
    )
    assert "&quot;" in map_link('http://host/path"value/')
    with pytest.raises(ValueError):
        base_url("http://host/app/", origin_only=True)


def test_http_client_bounds_and_redirects() -> None:
    with client_for("http://backend:8000") as client:
        assert client.timeout.connect == 5
        assert client.timeout.read == client.timeout.write == client.timeout.pool == 10
        assert not client.follow_redirects
        assert client.base_url == "http://backend:8000/"
