"""Turns raw fetch failures (HTTP codes, timeouts, anti-bot walls, DNS errors)
into plain language a non-technical reviewer can act on. The audit still needs
the technical detail, so it's preserved as a short parenthetical tail rather
than dropped — the difference is that the *lead* sentence explains what
happened and what to do, not what a 404 status code is.
"""

from __future__ import annotations

from urllib.parse import urlparse

from preapproval_tool.research.models import FetchResult


def _domain(url: str | None) -> str:
    if not url:
        return "the provider's website"
    netloc = urlparse(url).netloc
    return netloc or "the provider's website"


def _classify(raw: str) -> str | None:
    """Maps a raw fetch-attempt error to a plain-language explanation, or None
    if it doesn't match a known pattern (caller supplies a generic fallback).
    """
    text = raw.lower()
    if "404" in text or "not found" in text:
        return (
            "The exact web address listed on the application form doesn't exist "
            "anymore — the page returned “not found.” The provider may "
            "have changed or removed it. A reviewer should check the provider's "
            "current website for the right page."
        )
    if "403" in text or "forbidden" in text or "captcha" in text or "blocked" in text or "bot" in text:
        return (
            "The provider's website blocked our automated check (it screens out "
            "non-human visitors). This isn't a problem with the application — "
            "a reviewer can open the page manually to confirm the details."
        )
    if "timeout" in text or "timed out" in text:
        return (
            "The provider's website took too long to respond and the check timed "
            "out. It may be temporarily down or slow — a reviewer can retry, "
            "or open the page manually."
        )
    if "name or service not known" in text or "getaddrinfo" in text or "dns" in text or "no address" in text:
        return (
            "The web address on the application form couldn't be reached at all "
            "— it may be mistyped or no longer registered. A reviewer should "
            "confirm the provider's correct website."
        )
    if any(code in text for code in ("500", "502", "503", "504")):
        return (
            "The provider's website returned a server error, so we couldn't read "
            "it. It may be temporarily down — a reviewer can retry or open the "
            "page manually."
        )
    return None


def humanize_fetch_failure(fetch_result: FetchResult | None, url: str | None) -> str:
    """Reviewer-facing one-liner for why a page couldn't be read, with the raw
    technical reason kept as a short trailing detail for the audit trail.
    """
    domain = _domain(url)
    raw_reason = ""
    if fetch_result:
        raw_reason = "; ".join(a.error for a in fetch_result.attempts if a.error)

    friendly = _classify(raw_reason) if raw_reason else None
    if friendly is None:
        friendly = (
            f"We couldn't open {domain} to verify this automatically. A reviewer "
            "should open the page manually to confirm the details."
        )
    if raw_reason:
        return f"{friendly} (Technical detail: {raw_reason})"
    return friendly


__all__ = ["humanize_fetch_failure"]
