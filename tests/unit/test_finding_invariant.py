"""The single hard invariant this whole system leans on: a "found" status is
never trusted without a real evidence artifact attached. Enforced in
Finding.__post_init__ — this test exists so that invariant can never silently
regress in a refactor.
"""

from preapproval_tool.evaluation.models import Finding
from preapproval_tool.evidence.models import EvidenceItem
from datetime import datetime, timezone


def _evidence() -> EvidenceItem:
    return EvidenceItem(
        evidence_type="whole_page",
        criterion_id=None,
        label="Evidence: full page",
        url="https://example.org",
        captured_at=datetime.now(timezone.utc),
        method="playwright",
        file_path="/tmp/does-not-matter.png",
        content_hash="abc123",
    )


def test_found_without_evidence_is_downgraded():
    f = Finding("open_to_public", "Is it open to the public?", "found", "Looks fine.", evidence=[])
    assert f.status == "needs_review"
    assert "Automatically downgraded" in f.note


def test_found_with_evidence_is_kept():
    f = Finding("open_to_public", "Is it open to the public?", "found", "Looks fine.", evidence=[_evidence()])
    assert f.status == "found"


def test_reviewer_override_preserves_original_and_records_history():
    f = Finding("open_to_public", "Q", "needs_review", "System note.", evidence=[])
    f.apply_reviewer_override(status="found", note="Confirmed by phone call.")
    assert f.status == "found"  # reviewer override bypasses the evidence invariant intentionally
    assert f.original_status == "needs_review"
    assert f.original_note == "System note."
    assert f.reviewer_overridden is True
    assert f.reviewed is True
    assert len(f.history) == 1 and f.history[0].action == "override"


def test_restore_system_result_reverts_override():
    f = Finding("open_to_public", "Q", "needs_review", "System note.", evidence=[])
    f.apply_reviewer_override(status="found", note="Confirmed manually.")
    f.restore_system_result()
    assert f.status == "needs_review"
    assert f.note == "System note."
    assert f.reviewer_overridden is False
