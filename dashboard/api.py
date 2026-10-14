"""Client for the backend API."""

import httpx

COMPONENTS = ("database", "redis", "worker")


class ApiUnavailableError(Exception):
    """The API could not be reached or returned an unexpected response."""


def fetch_health(client: httpx.Client) -> dict[str, bool]:
    """Return whether each backing component is reachable, keyed by name."""
    try:
        response = client.get("/api/health/")
    except httpx.HTTPError as error:
        raise ApiUnavailableError(str(error)) from error

    # A 503 still carries a health report in its body.
    if response.status_code not in (200, 503):
        raise ApiUnavailableError(f"Health check failed with HTTP {response.status_code}")

    body = response.json()
    return {name: body.get(name) == "ok" for name in COMPONENTS}
