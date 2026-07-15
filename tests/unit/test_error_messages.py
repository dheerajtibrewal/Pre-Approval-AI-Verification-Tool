"""The reviewer-facing report must never leak raw plumbing ('Firecrawl
reported HTTP 404 for https://...') — it explains what happened in plain
language and keeps the technical string as a trailing detail for the audit."""

from preapproval_tool.research.error_messages import humanize_fetch_failure
from preapproval_tool.research.models import FetchAttempt, FetchResult


def _fr(error: str) -> FetchResult:
    return FetchResult(
        url="https://example.org/join",
        capture=None,
        attempts=[FetchAttempt(method="firecrawl", ok=False, error=error)],
    )


def test_404_is_explained_in_plain_language():
    msg = humanize_fetch_failure(_fr("HTTP 404 for https://example.org/join"), "https://example.org/join")
    assert "not found" in msg.lower()
    assert "404" not in msg.split("Technical detail")[0]  # no raw code in the lead
    assert "Technical detail: HTTP 404" in msg  # but preserved for the audit


def test_timeout_is_explained():
    msg = humanize_fetch_failure(_fr("Read timed out after 30s"), "https://example.org")
    assert "too long" in msg.lower() or "timed out" in msg.lower()


def test_blocked_is_explained():
    msg = humanize_fetch_failure(_fr("HTTP 403 Forbidden (captcha wall)"), "https://example.org")
    assert "blocked" in msg.lower()


def test_dns_failure_is_explained():
    msg = humanize_fetch_failure(_fr("getaddrinfo failed: Name or service not known"), "https://nope.example")
    assert "reached" in msg.lower() or "registered" in msg.lower()


def test_unknown_error_uses_generic_but_actionable_fallback():
    msg = humanize_fetch_failure(_fr("weird internal glitch xyz"), "https://example.org")
    assert "example.org" in msg
    assert "manually" in msg.lower()
    assert "Technical detail: weird internal glitch xyz" in msg


def test_no_attempts_still_returns_something_usable():
    msg = humanize_fetch_failure(None, "https://example.org")
    assert "example.org" in msg
