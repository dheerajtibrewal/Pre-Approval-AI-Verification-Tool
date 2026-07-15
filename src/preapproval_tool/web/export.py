"""Review & Export support: pre-export integrity validation and package
building. Kept separate from app.py since it's pure data logic, not routing.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import asdict
from pathlib import Path

from preapproval_tool.report.generator import write_report_pdf
from preapproval_tool.report.models import ReportData
from preapproval_tool.web.store import ApplicationRecord

_SECRET_MARKERS = ("sk-", "fc-", "api_key", "apikey", "secret")


def validate_export(report: ReportData | None) -> list[str]:
    """Runtime, defense-in-depth re-check before export — independent of the
    construction-time invariants in Finding/evidence capture, so a bug
    upstream can't silently produce an unvalidated export. Takes a ReportData
    directly so both the web app and the offline packaging path share one code
    path.
    """
    issues: list[str] = []
    if not report:
        return ["No report has been generated yet."]

    for f in report.web_findings:
        if f.status == "found" and not f.evidence:
            issues.append(f"'{f.criterion_id}' is Found but has no linked evidence.")
        for e in f.evidence:
            if not Path(e.file_path).exists():
                issues.append(f"Evidence file missing on disk for '{f.criterion_id}': {e.file_path}")

    text_blob = json.dumps({"note": [f.note for f in report.findings]})
    if any(marker in text_blob.lower() for marker in _SECRET_MARKERS):
        issues.append("A report field contains a string resembling an API key — review before sharing.")

    return issues


def _finding_to_dict(f) -> dict:
    d = asdict(f)
    d["evidence"] = [
        {
            "evidence_id": e.evidence_id,
            "evidence_type": e.evidence_type,
            "label": e.label,
            "url": e.url,
            "page_title": e.page_title,
            "captured_at": e.captured_at.isoformat(),
            "method": e.method,
            "file": Path(e.file_path).name,
        }
        for e in f.evidence
    ]
    return d


def build_report_json(report: ReportData) -> dict:
    return {
        "application_id": report.application_id,
        "category": report.category_display_name,
        "generated_at": report.generated_at.isoformat(),
        "participant_name": report.participant_name,
        "provider_name": report.provider_name,
        "item_name": report.item_name,
        "webpage_url": report.webpage_url,
        "source_domain": report.source_domain,
        "form_fee": report.form_fee,
        "summary_counts": report.summary_counts,
        "reviewed_count": report.reviewed_count,
        "total_reviewable": report.total_reviewable,
        "internal_reviewed_count": report.internal_reviewed_count,
        "total_internal": report.total_internal,
        "overall_reviewed_count": report.overall_reviewed_count,
        "overall_total": report.overall_total,
        "is_review_complete": report.is_review_complete,
        "fetch_error": report.fetch_error,
        "findings": [_finding_to_dict(f) for f in report.findings],
        "validation_issues": validate_export(report),
    }


def build_evidence_manifest(report: ReportData) -> dict:
    """A flat index of every evidence capture in the package: which finding(s)
    it backs, its source URL, capture time, method, and on-disk filename — so an
    auditor can tie each image back to a criterion without opening report.json."""
    items = []
    for e, criterion_ids in report.all_evidence:
        items.append(
            {
                "evidence_id": e.evidence_id,
                "evidence_type": e.evidence_type,
                "label": e.label,
                "file": f"evidence/{Path(e.file_path).name}",
                "url": e.url,
                "page_title": e.page_title,
                "captured_at": e.captured_at.isoformat(),
                "method": e.method,
                "supports_criteria": criterion_ids,
            }
        )
    return {"application_id": report.application_id, "evidence": items}


def build_run_metadata(report: ReportData) -> dict:
    """Top-level run metadata for the audit file — who/what/when plus the
    verdict counts and review-completion state at export time."""
    return {
        "application_id": report.application_id,
        "category": report.category_display_name,
        "provider_name": report.provider_name,
        "item_name": report.item_name,
        "participant_name": report.participant_name,
        "source_website": report.webpage_url,
        "generated_at": report.generated_at.isoformat(),
        "summary_counts": report.summary_counts,
        "internal_items": report.total_internal,
        "review_complete": report.is_review_complete,
        "research_note": report.research_note,
        "validation_issues": validate_export(report),
    }


def build_package_zip(record: ApplicationRecord) -> bytes:
    """Zips the run directory (static report.html + evidence/) plus the
    structured report.json, an evidence manifest, run metadata, and the
    reviewer-override/history state, into one self-contained audit download.
    """
    pdf_path = write_report_pdf(record.report, record.run_dir)  # type: ignore[arg-type]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in record.run_dir.rglob("*"):
            if path.is_file() and path.name not in ("source.pdf", "_report_print.html"):
                zf.write(path, arcname=path.relative_to(record.run_dir))
        zf.writestr("report.json", json.dumps(build_report_json(record.report), indent=2))
        zf.writestr("evidence-manifest.json", json.dumps(build_evidence_manifest(record.report), indent=2))
        zf.writestr("run-metadata.json", json.dumps(build_run_metadata(record.report), indent=2))
        zf.writestr("reviewer_overrides.json", json.dumps(record.review_state, indent=2))
    buf.seek(0)
    pdf_path.unlink(missing_ok=True)  # not left dangling in run_dir outside the zip
    return buf.read()


def write_full_package(report: ReportData, out_dir: Path) -> None:
    """Write the complete committable package next to an already-written
    report.html + evidence/: report.pdf, report.json, evidence-manifest.json,
    run-metadata.json. Same builders the web export zip uses, so the offline
    `scripts/run_sample.py` output and the in-app download can never drift.
    """
    out_dir = Path(out_dir)
    write_report_pdf(report, out_dir)
    (out_dir / "_report_print.html").unlink(missing_ok=True)  # temp render artifact
    (out_dir / "report.json").write_text(json.dumps(build_report_json(report), indent=2))
    (out_dir / "evidence-manifest.json").write_text(json.dumps(build_evidence_manifest(report), indent=2))
    (out_dir / "run-metadata.json").write_text(json.dumps(build_run_metadata(report), indent=2))
