"""SSRF guard: every provider URL taken from a form must pass through this
before any fetch/render call is made (Firecrawl or Playwright). Blocks
non-http(s) schemes and any hostname that resolves to a private, loopback,
link-local, or cloud-metadata address.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

_BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal"}


class UnsafeURLError(ValueError):
    """Raised when a URL fails the public-reachability/SSRF safety check."""


def _is_blocked_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def validate_public_url(url: str) -> str:
    """Raises UnsafeURLError if the URL is not a safe public http(s) target."""
    if not url or not isinstance(url, str):
        raise UnsafeURLError("No URL provided.")

    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"Unsupported URL scheme: {parsed.scheme or '(none)'}")
    if not parsed.hostname:
        raise UnsafeURLError("URL has no hostname.")
    if parsed.hostname.lower() in _BLOCKED_HOSTNAMES:
        raise UnsafeURLError(f"Blocked hostname: {parsed.hostname}")

    try:
        resolved = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Could not resolve hostname {parsed.hostname}: {exc}") from exc

    ips = {info[4][0] for info in resolved}
    if not ips:
        raise UnsafeURLError(f"No addresses resolved for {parsed.hostname}")
    for ip in ips:
        if _is_blocked_ip(ip):
            raise UnsafeURLError(
                f"{parsed.hostname} resolves to a non-public address ({ip}); refusing to fetch."
            )
    return parsed.geturl()
