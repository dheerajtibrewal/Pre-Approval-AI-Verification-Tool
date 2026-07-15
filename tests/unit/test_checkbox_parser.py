from pathlib import Path

from preapproval_tool.checklist_engine import get_checklist
from preapproval_tool.extraction.checkbox_parser import parse_checkbox_answers
from preapproval_tool.extraction.pdf_text import extract_pdf_text

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_01 = REPO_ROOT / "samples" / "Sample-01---Community-Class-GallopNYC.pdf"

EXPECTED = {
    "open_to_public": "yes",
    "published_fees": "yes",
    "fees_identical_opwdd": "yes",
    "subject_based": "yes",
    "no_college_credit": "no",
    "not_clinical": "no",
    "published_schedule": "yes",
    "fee_match": None,
    "budget_approved": "yes",
    "community_inclusion": "yes",
    "health_safety_fit": "yes",
    "independence_substitute": "yes",
    "exclusive_benefit": "no",
    "dd_only_setting": "no",
    "opwdd_staff_run": "no",
    "opwdd_grounds": "no",
    "duplicates_medicaid_services": "no",
    "duplicates_boe_services": "no",
    "reimbursed_directly": "no",
    "invoice_rule_context": None,
}


def test_parses_all_sample01_checkbox_answers_correctly():
    checklist = get_checklist("community-classes")
    pdf_text = extract_pdf_text(SAMPLE_01)
    answers = parse_checkbox_answers(pdf_text.full_text, checklist.criteria)
    assert answers == EXPECTED


def test_smart_quote_apostrophe_does_not_break_matching():
    """Regression test: the PDF uses a curly apostrophe (individual's) while
    the config used a straight one — this silently produced None instead of
    "yes" until the parser normalized quote characters.
    """
    checklist = get_checklist("community-classes")
    pdf_text = extract_pdf_text(SAMPLE_01)
    answers = parse_checkbox_answers(pdf_text.full_text, checklist.criteria)
    assert answers["health_safety_fit"] == "yes"
