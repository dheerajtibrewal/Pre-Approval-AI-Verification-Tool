"""fee_match's 'what's missing from the form' diagnostic: when an exact price
can't be pinned down, the note should name what the form left unspecified and
surface a grounded representative example — while honestly staying Needs
Review and never presenting the example as the confirmed price."""

from unittest.mock import patch

from preapproval_tool.checklist_engine.models import Criterion
from preapproval_tool.evaluation.fee_match import evaluate_fee_match


def _exact_criterion() -> Criterion:
    return Criterion(
        id="fee_match",
        question="Does the published fee match the form?",
        verifiable="web",
        check_type="fee_match",
        caps={"tolerance_pct": 0},
    )


def test_location_dependent_price_explains_missing_input_and_shows_example():
    with patch(
        "preapproval_tool.evaluation.fee_match._extract_published_amount",
        return_value={
            "published_amount": None,
            "quoted_snippet": None,
            "missing_input": "a specific club location",
            "example_amount": 15,
            "example_quote": "CLASSIC $15 /mo",
        },
    ):
        result = evaluate_fee_match(
            _exact_criterion(), form_fee=15, item_name="Classic Gym Membership", page_text="..."
        )
    assert result["status"] == "needs_review"
    assert "a specific club location" in result["note"]
    assert "$15" in result["note"]
    assert "illustrative" in result["note"]
    # The example is passed through as the snippet so it gets grounded + a
    # screenshot downstream — but the status is NOT found.
    assert result["quoted_snippet"] == "CLASSIC $15 /mo"


def test_no_price_and_no_example_stays_plain_needs_review():
    with patch(
        "preapproval_tool.evaluation.fee_match._extract_published_amount",
        return_value={
            "published_amount": None,
            "quoted_snippet": None,
            "missing_input": None,
            "example_amount": None,
            "example_quote": None,
        },
    ):
        result = evaluate_fee_match(
            _exact_criterion(), form_fee=15, item_name="Classic Gym Membership", page_text="..."
        )
    assert result["status"] == "needs_review"
    assert result["quoted_snippet"] is None
    assert "provider's website" in result["note"]


def test_location_specific_price_is_never_confirmed_as_the_applicants_price():
    """Sample 04: a Newark, NJ club's $15 must NOT be confirmed as the
    applicant's fee just because it numerically matches — the form doesn't say
    which club. It becomes a labelled example, held at Needs Review."""
    with patch(
        "preapproval_tool.evaluation.fee_match._extract_published_amount",
        return_value={
            "published_amount": 15,
            "quoted_snippet": "Classic $15/mo plus taxes & fees",
            "price_scope": "location_specific",
            "missing_input": "a specific club location",
            "example_amount": None,
            "example_quote": None,
        },
    ):
        result = evaluate_fee_match(
            _exact_criterion(), form_fee=15, item_name="Classic Gym Membership", page_text="..."
        )
    assert result["status"] == "needs_review"
    assert "Example price — not confirmed" in result["note"]
    assert "$15" in result["note"]


def test_tier_specific_price_under_a_cap_is_still_needs_review():
    from preapproval_tool.checklist_engine.models import Criterion

    cap_criterion = Criterion(
        id="fee_match", question="Fee within cap?", verifiable="web",
        check_type="fee_match", caps={"max": 111},
    )
    with patch(
        "preapproval_tool.evaluation.fee_match._extract_published_amount",
        return_value={
            "published_amount": 50, "quoted_snippet": "Premium plan $50",
            "price_scope": "tier_specific", "missing_input": "which plan/tier",
            "example_amount": None, "example_quote": None,
        },
    ):
        result = evaluate_fee_match(cap_criterion, form_fee=None, item_name="Coaching", page_text="...")
    assert result["status"] == "needs_review"


def test_universal_price_scope_still_confirms_normally():
    with patch(
        "preapproval_tool.evaluation.fee_match._extract_published_amount",
        return_value={
            "published_amount": 15, "quoted_snippet": "$15/mo",
            "price_scope": "universal", "missing_input": None,
            "example_amount": None, "example_quote": None,
        },
    ):
        result = evaluate_fee_match(
            _exact_criterion(), form_fee=15, item_name="Membership", page_text="..."
        )
    assert result["status"] == "found"


def test_exact_match_still_wins_when_a_single_price_is_found():
    with patch(
        "preapproval_tool.evaluation.fee_match._extract_published_amount",
        return_value={
            "published_amount": 15,
            "quoted_snippet": "$15/mo",
            "missing_input": None,
            "example_amount": None,
            "example_quote": None,
        },
    ):
        result = evaluate_fee_match(
            _exact_criterion(), form_fee=15, item_name="Classic Gym Membership", page_text="..."
        )
    assert result["status"] == "found"
