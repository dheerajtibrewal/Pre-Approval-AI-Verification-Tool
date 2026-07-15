"""Fallback fetch/render layer: a locally-driven headless browser.

Used only when Firecrawl fails. Also used (via `screenshot_element`) for
targeted, per-criterion evidence crops, since Firecrawl does not return DOM
element coordinates.
"""

from __future__ import annotations

from playwright.sync_api import sync_playwright

from preapproval_tool.research.models import PageCapture

_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# Common "accept" labels used by cookie-consent widgets (OneTrust, Cookiebot,
# Osano, Quantcast, and most homegrown banners). Tried in order, short timeout
# each, failures swallowed — most pages have no banner at all.
_CONSENT_ACCEPT_TEXTS = (
    "Accept All", "Accept all", "Accept All Cookies", "I Accept", "I agree",
    "Agree", "Allow All", "Allow all", "Got it", "OK", "Necessary only",
)

# CSS hide-fallback for banners that don't match a clickable "accept" label
# (custom copy, iframe-embedded widgets, etc.) — these are the container
# selectors most consent frameworks attach to the page.
_CONSENT_HIDE_CSS = """
[id*="cookie" i], [class*="cookie" i],
[id*="consent" i], [class*="consent" i],
#onetrust-consent-sdk, #onetrust-banner-sdk, .cookiebot, #CybotCookiebotDialog,
.osano-cm-window, .qc-cmp2-container {
  display: none !important;
  visibility: hidden !important;
}
"""


def _suppress_cookie_banners(page) -> None:
    """Best-effort: click a common "accept" button if present, then force-hide
    any remaining consent-banner containers via injected CSS. Fixed/sticky
    banners otherwise get baked into every screenshot taken while they're
    visible, regardless of which element was actually targeted.
    """
    for label in _CONSENT_ACCEPT_TEXTS:
        try:
            button = page.get_by_role("button", name=label, exact=False).first
            if button.count() > 0:
                button.click(timeout=1_000)
                page.wait_for_timeout(300)
                break
        except Exception:
            continue
    try:
        page.add_style_tag(content=_CONSENT_HIDE_CSS)
    except Exception:
        pass


class PlaywrightFetchError(RuntimeError):
    pass


def fetch_via_playwright(url: str, timeout_ms: int = 30_000) -> PageCapture:
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(user_agent=_DEFAULT_UA)
                response = page.goto(url, timeout=timeout_ms, wait_until="networkidle")
                if response is not None and response.status >= 400:
                    raise PlaywrightFetchError(
                        f"HTTP {response.status} loading {url}"
                    )
                _suppress_cookie_banners(page)
                text_content = page.inner_text("body")
                screenshot_bytes = page.screenshot(full_page=True)
                final_url = page.url
                page_title = page.title()
                try:
                    links = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
                except Exception:
                    links = []
            finally:
                browser.close()
    except PlaywrightFetchError:
        raise
    except Exception as exc:
        raise PlaywrightFetchError(f"Playwright fetch failed for {url}: {exc}") from exc

    return PageCapture(
        url=url,
        final_url=final_url,
        text_content=text_content,
        screenshot_bytes=screenshot_bytes,
        fetched_at=PageCapture.now(),
        method="playwright",
        page_title=page_title,
        links=links,
    )


def screenshot_element_by_text(
    url: str, needle: str, timeout_ms: int = 30_000
) -> bytes | None:
    """Best-effort targeted capture: screenshot the smallest element containing
    `needle` text. Returns None if the text can't be located (caller should
    fall back to a cropped region of the whole-page screenshot instead).
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(user_agent=_DEFAULT_UA)
                page.goto(url, timeout=timeout_ms, wait_until="networkidle")
                _suppress_cookie_banners(page)
                locator = page.get_by_text(needle, exact=False).first
                if locator.count() == 0:
                    return None
                locator.scroll_into_view_if_needed(timeout=5_000)
                return locator.screenshot()
            finally:
                browser.close()
    except Exception:
        return None
