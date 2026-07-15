"""Detects when a fetched page is an anti-bot wall / block screen rather than
the real content — so the tool reports "the provider blocked automated access"
honestly, instead of letting the LLM describe a CAPTCHA shell as a normal page.

Kept deliberately conservative (specific, well-known signatures + a very short
"shell" heuristic) so it never mislabels a real, thin page as blocked. Sample
07's Amazon "Click the button below to continue shopping" bot-check is the
motivating case.
"""

from __future__ import annotations

# Distinctive phrases that only appear on block/challenge screens, not on real
# product/marketing pages. Matched case-insensitively against the captured text.
_BLOCK_SIGNATURES = (
    "click the button below to continue shopping",  # Amazon bot wall
    "enter the characters you see below",           # Amazon CAPTCHA
    "type the characters you see in this image",
    "robot check",
    "are you a robot",
    "are you a human",
    "verify you are a human",
    "verifying you are human",
    "please verify you are a human",
    "complete the security check",
    "checking your browser before accessing",       # Cloudflare
    "ddos protection by cloudflare",
    "access denied",
    "access to this page has been denied",
    "you have been blocked",
    "unusual traffic from your computer network",    # Google
    "our systems have detected unusual traffic",
    "request was throttled",
    "rate limit exceeded",
    "too many requests",
    # NOTE: deliberately NOT a bare "captcha" substring. Legitimate, fully
    # working pages (esp. .edu / marketing sites — e.g. LaGuardia's continuing-ed
    # page) routinely embed Google reCAPTCHA on a search or newsletter form, so
    # their rendered text contains "captcha" without the page being blocked at
    # all. Matching it produced a false "provider blocked automated access"
    # verdict that suppressed real research. Real challenge screens are already
    # caught by the specific phrases above ("enter the characters you see below",
    # "robot check", "verify you are a human", …) and the tiny-shell heuristic.
)


def detect_blocked_page(text: str | None, title: str | None = None) -> str | None:
    """Returns a short human-readable reason if the page looks like a block/
    challenge screen, else None. The reason is phrased for a non-technical
    reviewer and never implies the real page was seen."""
    haystack = f"{title or ''}\n{text or ''}".lower()

    for sig in _BLOCK_SIGNATURES:
        if sig in haystack:
            return (
                "The provider blocked automated access (an anti-bot or CAPTCHA "
                "check was shown instead of the page), so the product and price "
                "could not be verified automatically. A reviewer should open the "
                "page manually to confirm the details."
            )

    # An almost-empty response with a "continue"/"enable JavaScript" nudge is a
    # classic anti-bot shell — flag only when the page is genuinely tiny so a
    # real but short page is never mislabelled.
    stripped = (text or "").strip()
    if len(stripped) < 200 and any(
        kw in haystack for kw in ("enable javascript", "continue shopping", "continue", "retry")
    ):
        return (
            "The provider returned an almost-empty page (likely an anti-bot or "
            "JavaScript challenge) rather than the real content, so the item "
            "could not be verified automatically. A reviewer should open the "
            "page manually to confirm the details."
        )
    return None


__all__ = ["detect_blocked_page"]
