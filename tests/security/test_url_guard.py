"""SSRF guard tests. Per the PM feedback: do not perform destructive testing
against real third-party sites — everything here is either a local/private
address (no external request made) or a scheme/hostname rejected before any
network call happens.
"""

import pytest

from preapproval_tool.security.url_guard import UnsafeURLError, validate_public_url


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8080/x",
        "http://127.0.0.1/",
        "http://127.0.0.1:9999/admin",
        "http://10.0.0.5/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data",  # cloud metadata endpoint
        "http://[::1]/",  # IPv6 loopback
        "file:///etc/passwd",
        "ftp://example.org/file",
        "javascript:alert(1)",
        "",
        None,
    ],
)
def test_blocks_unsafe_urls(url):
    with pytest.raises(UnsafeURLError):
        validate_public_url(url)


def test_blocks_url_with_no_hostname():
    with pytest.raises(UnsafeURLError):
        validate_public_url("http:///path-only")


@pytest.mark.network
def test_allows_a_real_public_https_url():
    # Requires network/DNS — the fetch layer itself is still gated separately
    # by Firecrawl/Playwright timeouts and error handling.
    result = validate_public_url("https://example.com/some-page")
    assert result.startswith("https://example.com")
