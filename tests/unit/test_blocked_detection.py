"""Blocked/anti-bot page detection (Sample 07: Amazon's bot-check shell was
described as a normal navigation page). Detection must be conservative — never
flag a real, thin page as blocked."""

from preapproval_tool.research.blocked_detection import detect_blocked_page


def test_amazon_continue_shopping_bot_wall_is_flagged():
    reason = detect_blocked_page("Click the button below to continue shopping", "Amazon.com")
    assert reason is not None
    assert "blocked automated access" in reason


def test_captcha_and_cloudflare_are_flagged():
    assert detect_blocked_page("Enter the characters you see below (CAPTCHA)") is not None
    assert detect_blocked_page("Checking your browser before accessing the site") is not None
    assert detect_blocked_page("Access Denied — you don't have permission") is not None


def test_tiny_anti_bot_shell_is_flagged():
    assert detect_blocked_page("Please enable JavaScript to continue") is not None


def test_real_product_page_is_not_flagged():
    real = (
        "Stainless Steel Grab Bar, 24 inch. Price: $27.99. Rated 4.7 stars. "
        "Mounting hardware included. Supports up to 500 lbs. Ships in 2 days. "
        "Customer reviews and product specifications follow with full detail."
    )
    assert detect_blocked_page(real, "Amazon.com: Grab Bar") is None


def test_real_but_short_page_without_challenge_keywords_is_not_flagged():
    # A short page that doesn't contain a challenge keyword must not be flagged.
    assert detect_blocked_page("Welcome to our small gym.", "Home") is None


def test_empty_input_is_safe():
    assert detect_blocked_page(None, None) is None
    assert detect_blocked_page("", "") is None


def test_working_page_that_merely_embeds_recaptcha_is_not_flagged():
    # Regression (Sample 09 LaGuardia): a legitimate, fully-rendered page that
    # embeds a Google reCAPTCHA widget on a search/newsletter form must NOT be
    # reported as a blocked/anti-bot wall. A bare "captcha" substring used to
    # trip this, wrongly suppressing real research and leaving a near-blank
    # capture.
    real_edu_page = (
        "Continuing Education — LaGuardia Community College. Explore Career "
        "Skills & Workforce Training, English Language Learning, Pre-College "
        "programs, and more. Register for a course or view our catalog. "
        "Newsletter signup protected by reCAPTCHA. Privacy Policy and Terms apply."
    )
    assert detect_blocked_page(real_edu_page, "Continuing Education | LaGuardia") is None
