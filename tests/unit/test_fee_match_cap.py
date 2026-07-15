"""fee_match's cap-ceiling mode (used by Coaching/Transition Program-style
"fee must be <= $X" caps, as distinct from Community Classes/Memberships'
exact-match-with-tolerance mode). The LLM extraction call is mocked so this
test is deterministic and offline.
"""

from unittest.mock import patch

from preapproval_tool.checklist_engine.models import Criterion
from preapproval_tool.evaluation.fee_match import evaluate_fee_match


def _cap_criterion(max_cap: float) -> Criterion:
    return Criterion(
        id="fee_match",
        question="Is the fee within the cap?",
        verifiable="web",
        check_type="fee_match",
        evidence_label="Evidence: fee vs. cap",
        caps={"max": max_cap},
    )


def test_published_price_within_cap_is_found():
    with patch(
        "preapproval_tool.evaluation.fee_match._extract_published_amount",
        return_value={"published_amount": 50, "quoted_snippet": "$50 per class"},
    ):
        result = evaluate_fee_match(
            _cap_criterion(111), form_fee=50, item_name="Parenting coaching", page_text="..."
        )
    assert result["status"] == "found"
    assert "within" in result["note"]


def test_published_price_over_cap_is_not_found():
    with patch(
        "preapproval_tool.evaluation.fee_match._extract_published_amount",
        return_value={"published_amount": 200, "quoted_snippet": "$200 per class"},
    ):
        result = evaluate_fee_match(
            _cap_criterion(111), form_fee=200, item_name="Parenting coaching", page_text="..."
        )
    assert result["status"] == "not_found"
    assert "exceeds" in result["note"]


def test_falls_back_to_form_fee_when_no_published_price_found():
    with patch(
        "preapproval_tool.evaluation.fee_match._extract_published_amount",
        return_value={"published_amount": None, "quoted_snippet": None},
    ):
        result = evaluate_fee_match(
            _cap_criterion(350), form_fee=300, item_name="LaGuardia ACE", page_text="..."
        )
    assert result["status"] == "found"
    assert "Form-stated fee" in result["note"]


def test_no_amount_available_at_all_is_needs_review():
    with patch(
        "preapproval_tool.evaluation.fee_match._extract_published_amount",
        return_value={"published_amount": None, "quoted_snippet": None},
    ):
        result = evaluate_fee_match(
            _cap_criterion(350), form_fee=None, item_name="LaGuardia ACE", page_text="..."
        )
    assert result["status"] == "needs_review"
