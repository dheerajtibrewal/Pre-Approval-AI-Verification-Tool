"""Regression test for a real bug found during manual QA on Sample 10
(graciebarra.com): targeted evidence screenshots showed a fixed-position
cookie-consent banner instead of the actual proof text, because nothing in
the Playwright fetch/capture path ever dismissed or hid consent banners.
See log.md Key Learnings for the full root-cause writeup.

Uses a local HTML fixture (no live network) so this stays fast and
deterministic while still exercising the real Playwright suppression code.
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

from preapproval_tool.research.playwright_client import (
    _suppress_cookie_banners,
    screenshot_element_by_text,
)

_FIXTURE_HTML = """
<!doctype html>
<html><head><style>
  .cookie-consent-banner {
    position: fixed; top: 0; left: 0; right: 0; height: 200px;
    background: navy; color: white; z-index: 9999;
  }
</style></head>
<body>
  <div class="cookie-consent-banner" id="onetrust-banner-sdk">
    This website uses cookies. We use cookies to personalise content and ads.
  </div>
  <p id="proof">Jiu-Jitsu is open to everyone in the community.</p>
</body></html>
"""


def _write_fixture(tmp_path: Path) -> str:
    fixture = tmp_path / "cookie_banner_fixture.html"
    fixture.write_text(_FIXTURE_HTML, encoding="utf-8")
    return fixture.resolve().as_uri()


def test_suppress_cookie_banners_hides_fixed_position_banner(tmp_path):
    url = _write_fixture(tmp_path)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(url)
            assert page.locator(".cookie-consent-banner").is_visible()
            _suppress_cookie_banners(page)
            assert not page.locator(".cookie-consent-banner").is_visible()
        finally:
            browser.close()


def test_targeted_screenshot_excludes_banner_overlay(tmp_path):
    """The bug's real symptom: a crop of unrelated proof text must not
    include the banner's pixels just because the banner was on-screen."""
    url = _write_fixture(tmp_path)
    image_bytes = screenshot_element_by_text(url, "open to everyone")
    assert image_bytes is not None
    # The banner is navy (0, 0, 128); the crop should be dominated by the
    # paragraph's default white background, not the banner's fixed overlay.
    from PIL import Image
    import io

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    navy_pixels = sum(
        1
        for pixel in img.getdata()
        if pixel[0] < 20 and pixel[1] < 20 and 100 < pixel[2] < 160
    )
    assert navy_pixels / (img.width * img.height) < 0.05
