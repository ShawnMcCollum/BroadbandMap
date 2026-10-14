from collections.abc import Callable

import httpx
import pytest

from api import ApiUnavailableError, fetch_health


def client_for(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(base_url="http://api", transport=httpx.MockTransport(handler))


def test_all_components_up() -> None:
    body = {"status": "ok", "database": "ok", "redis": "ok", "worker": "ok"}
    client = client_for(lambda _: httpx.Response(200, json=body))

    assert fetch_health(client) == {"database": True, "redis": True, "worker": True}


def test_unreachable_component() -> None:
    body = {"status": "error", "database": "ok", "redis": "ok", "worker": "unreachable"}
    client = client_for(lambda _: httpx.Response(503, json=body))

    assert fetch_health(client) == {"database": True, "redis": True, "worker": False}


def test_unexpected_status() -> None:
    client = client_for(lambda _: httpx.Response(502))

    with pytest.raises(ApiUnavailableError, match="HTTP 502"):
        fetch_health(client)


def test_connection_error() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ApiUnavailableError):
        fetch_health(client_for(refuse))
