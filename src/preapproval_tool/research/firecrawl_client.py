"""Primary fetch/render layer: Firecrawl.

Firecrawl renders the page server-side (handling JS rendering and anti-bot
measures that a bare headless browser run from a datacenter IP would often
trip on — notably Amazon product pages) and returns clean markdown text plus
a full-page screenshot in one call. See docs/limitations-and-assumptions.md
and the Phase 1 plan (§8/§13) for why this is the primary path and Playwright
is the fallback, not the other way around.
"""

from __future__ import annotations

import os
from functools import lru_cache

import requests
from firecrawl import Firecrawl
from firecrawl.v2.types import ExecuteJavascriptAction, ScreenshotFormat

from preapproval_tool.research.models import PageCapture

# Force-hide cookie-consent banners before Firecrawl captures the screenshot/
# markdown — otherwise a fixed-position banner renders on top of the real
# content in every screenshot, and its text pollutes the extracted markdown
# that criterion evaluation reads. Runs as a page action, so it applies to
# the final rendered state Firecrawl captures for both formats.
_HIDE_COOKIE_BANNERS_JS = """
(() => {
  const style = document.createElement('style');
  style.textContent = `
    [id*="cookie" i], [class*="cookie" i],
    [id*="consent" i], [class*="consent" i],
    #onetrust-consent-sdk, #onetrust-banner-sdk, .cookiebot, #CybotCookiebotDialog,
    .osano-cm-window, .qc-cmp2-container {
      display: none !important;
      visibility: hidden !important;
    }
  `;
  document.head.appendChild(style);
})();
"""


class FirecrawlUnavailableError(RuntimeError):
    """Raised when Firecrawl is not configured or the scrape call fails."""


@lru_cache(maxsize=1)
def _client() -> Firecrawl:
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key or api_key.startswith("fc-replace-me"):
        raise FirecrawlUnavailableError(
            "FIRECRAWL_API_KEY is not set. Copy .env.example to .env and add a real key."
        )
    return Firecrawl(api_key=api_key)


def fetch_via_firecrawl(url: str, timeout_ms: int = 30_000) -> PageCapture:
    try:
        doc = _client().scrape(
            url,
            formats=["markdown", "links", ScreenshotFormat(full_page=True)],
            only_main_content=False,
            timeout=timeout_ms,
            block_ads=True,
            actions=[ExecuteJavascriptAction(script=_HIDE_COOKIE_BANNERS_JS)],
        )
    except Exception as exc:  # Firecrawl raises its own exception hierarchy
        raise FirecrawlUnavailableError(f"Firecrawl scrape failed for {url}: {exc}") from exc

    if not doc.markdown and not doc.screenshot:
        raise FirecrawlUnavailableError(f"Firecrawl returned no content for {url}")

    screenshot_bytes = b""
    if doc.screenshot:
        resp = requests.get(doc.screenshot, timeout=30)
        resp.raise_for_status()
        screenshot_bytes = resp.content

    final_url = url
    status_code = None
    page_title = ""
    if doc.metadata:
        final_url = doc.metadata.source_url or url
        status_code = doc.metadata.status_code
        page_title = doc.metadata.title or ""

    if status_code and status_code >= 400:
        raise FirecrawlUnavailableError(f"Firecrawl reported HTTP {status_code} for {url}")

    return PageCapture(
        url=url,
        final_url=final_url,
        text_content=doc.markdown or "",
        screenshot_bytes=screenshot_bytes,
        fetched_at=PageCapture.now(),
        method="firecrawl",
        page_title=page_title,
        links=list(doc.links or []),
    )
