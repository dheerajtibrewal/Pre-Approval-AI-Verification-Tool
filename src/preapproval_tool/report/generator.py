"""Assembles a ReportData object from an evaluation run and renders it to a
self-contained HTML report package (report.html + evidence/ next to it).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from preapproval_tool.checklist_engine.models import ChecklistConfig
from preapproval_tool.evaluation.evaluator import EvaluationRun
from preapproval_tool.extraction.models import ExtractedApplication
from preapproval_tool.report.models import ReportData

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "web" / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)
_env.filters["evidence_rel_path"] = lambda item: f"evidence/{Path(item.file_path).name}"

_STATUS_LABELS = {
    "found": "Found",
    "not_found": "Not Found",
    "needs_review": "Needs Review",
    "internal": "Internal — Not Website-Verifiable",
}


def build_report_data(
    checklist: ChecklistConfig,
    extracted: ExtractedApplication,
    run: EvaluationRun,
    *,
    application_id: str | None = None,
    appeal_denial_reason: str | None = None,
) -> ReportData:
    fee_value = extracted.value(checklist.fee_field) if checklist.fee_field else None
    return ReportData(
        application_id=application_id or str(uuid.uuid4())[:8],
        category_display_name=checklist.display_name,
        generated_at=datetime.now(timezone.utc),
        participant_name=extracted.value("participant_name"),
        provider_name=extracted.value("provider_name"),
        item_name=(
            extracted.value(checklist.item_name_field) if checklist.item_name_field else None
        ),
        webpage_url=extracted.value("webpage_url") or extracted.value("item_link"),
        form_fee=f"${fee_value:g}" if fee_value is not None else None,
        findings=run.findings,
        fetch_error=run.fetch_error,
        low_confidence_fields=extracted.low_confidence_fields,
        warnings=extracted.warnings,
        appeal_denial_reason=appeal_denial_reason,
        research_note=run.research_note,
    )


def render_report_html(
    report: ReportData,
    *,
    interactive: bool = False,
    app_id: str | None = None,
    pdf_mode: bool = False,
) -> str:
    template = _env.get_template("report.html")
    return template.render(
        report=report,
        status_labels=_STATUS_LABELS,
        interactive=interactive,
        app_id=app_id,
        pdf_mode=pdf_mode,
    )


def write_report_package(report: ReportData, run_dir: str | Path) -> Path:
    """Writes the frozen, non-interactive report — this is the standalone,
    shareable deliverable (Brief §6): no edit controls, since a static file
    has no server behind it to receive them.
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    html = render_report_html(report, interactive=False)
    out_path = run_dir / "report.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


def write_report_pdf(report: ReportData, run_dir: str | Path) -> Path:
    """Renders the report to a single, self-contained, paginated PDF — the
    recommended "hand this to a non-technical reviewer" deliverable
    (Brief §6: "a shareable report... bundled so a reviewer can save and
    share them"). Reuses the exact same template/CSS as the live reviewer
    view (one source of truth for layout) via a dedicated `pdf_mode` render
    that unrolls every tab into one linear document instead of hiding all
    but the active one, and via Playwright's `page.pdf()` rather than a
    separate PDF-generation library — Playwright is already a hard
    dependency of this project for browser automation.
    """
    from playwright.sync_api import sync_playwright

    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    html = render_report_html(report, interactive=False, pdf_mode=True)
    # Written next to evidence/ so the report's relative <img src="evidence/...">
    # references resolve when opened via a file:// URL, exactly like report.html.
    print_html_path = run_dir / "_report_print.html"
    print_html_path.write_text(html, encoding="utf-8")

    pdf_path = run_dir / "report.pdf"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.goto(print_html_path.resolve().as_uri())
                page.wait_for_load_state("networkidle")
                # page.pdf() does NOT implicitly apply @media print — without
                # this, every print-only override in report.html's stylesheet
                # (full-width panels, hidden interactive chrome, tighter
                # spacing) is silently skipped and the PDF renders using the
                # screen layout instead, leaving ~35-40% of every page blank.
                page.emulate_media(media="print")
                page.pdf(
                    path=str(pdf_path),
                    format="Letter",
                    print_background=True,
                    margin={"top": "0.4in", "bottom": "0.4in", "left": "0.3in", "right": "0.3in"},
                )
            finally:
                browser.close()
    finally:
        print_html_path.unlink(missing_ok=True)
    return pdf_path
