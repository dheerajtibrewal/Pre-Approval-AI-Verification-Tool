"""The exclusion-list gate is deterministic — no LLM involved. Sample 07's
laptop (must be flagged, matching "Computer Hardware") and Sample 06's grab
bar (must pass clean) are the two named test cases from the brief.
"""

from preapproval_tool.checklist_engine.models import Criterion
from preapproval_tool.evaluation.exclusion_list import evaluate_exclusion_list

HRI_EXCLUSIONS = [
    "Academic Tutoring",
    "Automatic Pill Dispenser/Medication System",
    "Cell Phones/Telephones",
    "Computer Hardware",
    "Computer Programs/Software",
    "Leased & Purchased Vehicles",
    "Health-Related Services/Equipment/Supplies",
    "Parent/Participant/Staff Activity Fees, Expenses & Meals",
    "Personal Monitoring Systems",
    "Direct Clinician services & therapies (OT, PT, Speech, Psychology) and experimental therapies",
]


def _criterion() -> Criterion:
    return Criterion(
        id="not_excluded",
        question="Item plausibly not on exclusion list?",
        verifiable="web",
        check_type="exclusion_list",
        evidence_label="Evidence: item listing",
        exclusion_list=HRI_EXCLUSIONS,
    )


def test_laptop_is_flagged_as_excluded():
    result = evaluate_exclusion_list(_criterion(), item_name="Laptop computer")
    assert result["status"] == "not_found"
    assert "computer" in result["note"].lower()


def test_grab_bar_passes_clean():
    result = evaluate_exclusion_list(_criterion(), item_name="Bathroom safety grab bar (wall-mounted)")
    assert result["status"] == "found"


def test_never_calls_llm():
    """Structural guarantee: this module must not import the LLM client —
    exclusion-list gating has to stay a deterministic, auditable rule.
    """
    import inspect

    import preapproval_tool.evaluation.exclusion_list as mod

    source = inspect.getsource(mod)
    assert "preapproval_tool.llm" not in source
    assert "structured_completion" not in source
