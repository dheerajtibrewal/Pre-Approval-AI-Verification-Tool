"""Regression test for a real UX bug caught during manual QA (Sample 07,
2026-07-15): the "Mark reviewed"/"Mark completed" button stayed visible and
clickable after already being clicked, with no visible state change and no
way to undo — clicking it again was a silent no-op. Fixed by hiding it once
`reviewed` is true and showing an "Undo"/"Restore" action instead.

No LLM/network calls — builds a report from fabricated Finding/ReportData
objects directly, bypassing the real research pipeline.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import preapproval_tool.web.app as app_mod
from preapproval_tool.evaluation.models import Finding
from preapproval_tool.report.models import ReportData
from preapproval_tool.web.store import ApplicationRecord, store


@pytest.fixture
def client():
    return TestClient(app_mod.app)


def _record_with_findings(tmp_path) -> ApplicationRecord:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    record = ApplicationRecord(
        id="testapp01",
        pdf_filename="test.pdf",
        pdf_path=run_dir / "source.pdf",
        run_dir=run_dir,
    )
    web_finding = Finding(
        criterion_id="open_to_public",
        question="Is it open to the public?",
        status="needs_review",
        note="No info available.",
    )
    internal_finding = Finding(
        criterion_id="budget_approved",
        question="Is this approved in the budget?",
        status="internal",
        note="Requires the approved budget record.",
        group="Budget and funding",
    )
    record.report = ReportData(
        application_id="testapp01",
        category_display_name="Household Related Items",
        generated_at=datetime.now(timezone.utc),
        participant_name="Test P.",
        provider_name=None,
        item_name="Test Item",
        webpage_url="https://example.org",
        form_fee=None,
        findings=[web_finding, internal_finding],
        fetch_error=None,
    )
    record.stage = "reported"
    store._records[record.id] = record
    return record


def test_mark_reviewed_button_disappears_after_marking_reviewed(client, tmp_path):
    record = _record_with_findings(tmp_path)

    before = client.get(f"/applications/{record.id}/report")
    assert "Mark reviewed" in before.text

    client.post(f"/applications/{record.id}/findings/open_to_public/mark-reviewed")

    after = client.get(f"/applications/{record.id}/report")
    assert "Undo (mark as not reviewed)" in after.text
    # The exact "Mark reviewed" button for this finding must be gone, not just
    # relabeled — a stale action button showing after the state already
    # changed was the reported bug.
    assert 'action="/applications/testapp01/findings/open_to_public/mark-reviewed"' not in after.text


def test_undo_restores_mark_reviewed_button(client, tmp_path):
    record = _record_with_findings(tmp_path)
    client.post(f"/applications/{record.id}/findings/open_to_public/mark-reviewed")
    client.post(f"/applications/{record.id}/findings/open_to_public/restore")

    after = client.get(f"/applications/{record.id}/report")
    assert 'action="/applications/testapp01/findings/open_to_public/mark-reviewed"' in after.text
    assert "Undo (mark as not reviewed)" not in after.text


def test_overridden_finding_shows_restore_not_undo(client, tmp_path):
    record = _record_with_findings(tmp_path)
    client.post(
        f"/applications/{record.id}/findings/open_to_public/override",
        data={"status": "found", "note": "Confirmed manually."},
    )

    after = client.get(f"/applications/{record.id}/report")
    assert "Restore system result" in after.text
    assert "Undo (mark as not reviewed)" not in after.text


def test_internal_mark_completed_button_disappears_after_completing(client, tmp_path):
    record = _record_with_findings(tmp_path)

    before = client.get(f"/applications/{record.id}/report")
    assert "Mark completed" in before.text

    client.post(f"/applications/{record.id}/findings/budget_approved/mark-reviewed")

    after = client.get(f"/applications/{record.id}/report")
    assert "Undo (mark as not completed)" in after.text
    assert 'action="/applications/testapp01/findings/budget_approved/mark-reviewed"' not in after.text
