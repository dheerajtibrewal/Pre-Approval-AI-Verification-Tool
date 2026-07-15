"""The exported .zip must be a self-contained audit package: report.pdf,
report.html, report.json, evidence-manifest.json, run-metadata.json, the
evidence/ files, and reviewer overrides — and every evidence file the report
references must actually be present. No live network/LLM calls."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from preapproval_tool.evaluation.models import Finding
from preapproval_tool.evidence.models import EvidenceItem
from preapproval_tool.report.generator import write_report_package
from preapproval_tool.report.models import ReportData
from preapproval_tool.web.export import build_package_zip
from preapproval_tool.web.store import ApplicationRecord


def _record_with_evidence(tmp_path: Path) -> ApplicationRecord:
    run_dir = tmp_path / "run"
    (run_dir / "evidence").mkdir(parents=True)
    ev_file = run_dir / "evidence" / "whole-page-x.png"
    ev_file.write_bytes(b"\x89PNG\r\n\x1a\n fake png bytes")

    evidence = EvidenceItem(
        evidence_type="whole_page", criterion_id=None, label="Full page as reviewed",
        url="https://example.org", captured_at=datetime.now(timezone.utc), method="firecrawl",
        file_path=str(ev_file), content_hash="abc123", page_title="Example",
    )
    report = ReportData(
        application_id="exp01", category_display_name="Community Class",
        generated_at=datetime.now(timezone.utc), participant_name="P.", provider_name="Prov",
        item_name="Item", webpage_url="https://example.org", form_fee="$30",
        findings=[
            Finding("open", "Open to public?", "needs_review", "n", evidence=[evidence]),
            Finding("budget", "Budget approved?", "internal", "needs record", group="Budget"),
        ],
        fetch_error=None,
    )
    # The static report.html is written into run_dir so the zip picks it up.
    write_report_package(report, run_dir)
    record = ApplicationRecord(
        id="exp01", pdf_filename="s.pdf", pdf_path=run_dir / "source.pdf", run_dir=run_dir
    )
    record.report = report
    return record


def test_zip_contains_every_required_member_and_referenced_files_exist(tmp_path):
    record = _record_with_evidence(tmp_path)
    data = build_package_zip(record)

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        for required in (
            "report.pdf", "report.html", "report.json",
            "evidence-manifest.json", "run-metadata.json", "reviewer_overrides.json",
        ):
            assert required in names, f"missing {required} in {names}"

        # Every evidence file the manifest references must exist in the zip.
        manifest = json.loads(zf.read("evidence-manifest.json"))
        assert manifest["evidence"], "manifest should list at least one capture"
        for item in manifest["evidence"]:
            assert item["file"] in names, f"referenced {item['file']} not in package"

        # report.json's referenced evidence files must exist too.
        report_json = json.loads(zf.read("report.json"))
        for f in report_json["findings"]:
            for e in f["evidence"]:
                assert f"evidence/{e['file']}" in names


def test_static_html_in_package_has_no_server_only_links(tmp_path):
    record = _record_with_evidence(tmp_path)
    data = build_package_zip(record)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        html = zf.read("report.html").decode("utf-8")
    assert "/applications/" not in html  # no /applications/None/export/... etc.
