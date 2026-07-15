from datetime import datetime, timezone
from pathlib import Path

from preapproval_tool.evaluation.models import Finding
from preapproval_tool.evidence.models import EvidenceItem
from preapproval_tool.report.models import ReportData
from preapproval_tool.web.export import validate_export
from preapproval_tool.web.store import ApplicationRecord


def _record_with_findings(findings, run_dir: Path) -> ApplicationRecord:
    record = ApplicationRecord(
        id="test123",
        pdf_filename="test.pdf",
        pdf_path=run_dir / "source.pdf",
        run_dir=run_dir,
    )
    record.report = ReportData(
        application_id="test123",
        category_display_name="Community Class",
        generated_at=datetime.now(timezone.utc),
        participant_name="Test P.",
        provider_name="Test Provider",
        item_name="Test Class",
        webpage_url="https://example.org",
        form_fee="$80",
        findings=findings,
        fetch_error=None,
    )
    return record


def test_flags_missing_evidence_file_on_disk(tmp_path):
    evidence = EvidenceItem(
        evidence_type="whole_page",
        criterion_id=None,
        label="Evidence: full page",
        url="https://example.org",
        captured_at=datetime.now(timezone.utc),
        method="playwright",
        file_path=str(tmp_path / "does-not-exist.png"),
        content_hash="abc123",
    )
    finding = Finding("open_to_public", "Q", "found", "note", evidence=[evidence])
    record = _record_with_findings([finding], tmp_path)
    issues = validate_export(record.report)
    assert any("missing on disk" in i for i in issues)


def test_clean_report_has_no_issues(tmp_path):
    evidence_path = tmp_path / "evidence.png"
    evidence_path.write_bytes(b"fake-png-bytes")
    evidence = EvidenceItem(
        evidence_type="whole_page",
        criterion_id=None,
        label="Evidence: full page",
        url="https://example.org",
        captured_at=datetime.now(timezone.utc),
        method="playwright",
        file_path=str(evidence_path),
        content_hash="abc123",
    )
    finding = Finding("open_to_public", "Q", "found", "note", evidence=[evidence])
    record = _record_with_findings([finding], tmp_path)
    assert validate_export(record.report) == []


def test_no_report_yet_is_reported_as_an_issue(tmp_path):
    record = ApplicationRecord(
        id="test456", pdf_filename="test.pdf", pdf_path=tmp_path / "source.pdf", run_dir=tmp_path
    )
    issues = validate_export(record.report)
    assert len(issues) == 1
