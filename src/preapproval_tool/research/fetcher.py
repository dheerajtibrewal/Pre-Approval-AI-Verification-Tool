"""Two-tier fetch strategy: SSRF-validate the URL, try Firecrawl, fall back to
Playwright, and only then report a page as inaccessible. Every attempt (success
or failure) is recorded on the FetchResult for the evidence/audit trail —
never a silent failure.
"""

from __future__ import annotations

from preapproval_tool.research.firecrawl_client import (
    FirecrawlUnavailableError,
    fetch_via_firecrawl,
)
from preapproval_tool.research.models import FetchAttempt, FetchResult
from preapproval_tool.research.playwright_client import (
    PlaywrightFetchError,
    fetch_via_playwright,
)
from preapproval_tool.security.url_guard import UnsafeURLError, validate_public_url


def fetch_page(url: str) -> FetchResult:
    safe_url = validate_public_url(url)  # raises UnsafeURLError — caller should let it propagate
    attempts: list[FetchAttempt] = []

    try:
        capture = fetch_via_firecrawl(safe_url)
        attempts.append(FetchAttempt(method="firecrawl", ok=True))
        return FetchResult(url=safe_url, capture=capture, attempts=attempts)
    except FirecrawlUnavailableError as exc:
        attempts.append(FetchAttempt(method="firecrawl", ok=False, error=str(exc)))

    try:
        capture = fetch_via_playwright(safe_url)
        attempts.append(FetchAttempt(method="playwright", ok=True))
        return FetchResult(url=safe_url, capture=capture, attempts=attempts)
    except PlaywrightFetchError as exc:
        attempts.append(FetchAttempt(method="playwright", ok=False, error=str(exc)))

    return FetchResult(url=safe_url, capture=None, attempts=attempts)


__all__ = ["fetch_page", "UnsafeURLError"]
