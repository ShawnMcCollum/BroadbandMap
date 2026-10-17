"""Validated HTTP destinations; only the API origin is used for server requests."""

import html
from urllib.parse import urlsplit, urlunsplit


def base_url(value: str, *, origin_only: bool = False) -> str:
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme in ("http", "https")
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and (not origin_only or parsed.path in ("", "/"))
        )
        _ = parsed.port
    except ValueError:
        valid = False
    if not valid or "\\" in value or any(ord(c) <= 32 or ord(c) == 127 for c in value):
        raise ValueError("Use an HTTP(S) base URL without credentials, query or fragment.")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/") + "/", "", ""))


def map_link(value: str) -> str:
    destination = base_url(value) + "#/map"
    return f'<a href="{html.escape(destination, quote=True)}" target="_self">Map</a>'
