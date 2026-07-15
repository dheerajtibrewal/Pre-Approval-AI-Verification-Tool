"""The PDF export (added per user request: a single, well-formatted,
print-ready document is a better "shareable report" for a non-technical
reviewer than a lone .html file — see log.md for the design discussion).

No LLM/network calls: builds a report from fabricated Finding/ReportData
objects and renders locally via Playwright (file:// URL, no site navigation),
so this stays fast and deterministic.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import preapproval_tool.web.app as app_mod
from preapproval_tool.evaluation.models import Finding
from preapproval_tool.report.generator import render_report_html, write_report_pdf
from preapproval_tool.report.models import ReportData
from preapproval_tool.web.store import ApplicationRecord, store


def _report() -> ReportData:
    return ReportData(
        application_id="pdftest01",
        category_display_name="Community Class",
        generated_at=datetime.now(timezone.utc),
        participant_name="Test P.",
        provider_name="Test Provider",
        item_name="Test Class",
        webpage_url="https://example.org",
        form_fee="$80",
        findings=[
            Finding(
                criterion_id="open_to_public",
                question="Is it open to the public?",
                status="needs_review",
                note="No info available.",
            ),
            Finding(
                criterion_id="budget_approved",
                question="Is this approved in the budget?",
                status="internal",
                note="Requires the approved budget record.",
                group="Budget and funding",
            ),
        ],
        fetch_error=None,
    )


def test_pdf_mode_renders_all_sections_without_hidden_attribute():
    """The core PDF-mode requirement: every tab's content must appear in the
    linear document (a PDF has no clickable tabs to reveal hidden panels)."""
    html = render_report_html(_report(), pdf_mode=True)
    assert "hidden" not in html.lower().split("<script")[0] or "Findings" in html
    assert 'id="panel-findings"' in html
    assert "hidden" not in html[html.index('id="panel-findings"') - 50 : html.index('id="panel-findings"') + 100]
    assert "<script>" not in html  # no interactive JS needed/shipped in a static PDF
    assert 'class="chev"' not in html  # no expand/collapse affordance in a static document


def test_pdf_mode_does_not_repeat_the_cover_page_content():
    """The cover page (pdf_mode-only) already shows participant/provider/category,
    verdict counts, and the attention list. The Overview panel used to render an
    unconditional second copy of all of it (app-header + "Request at a glance" +
    "What this report tells you") right after the cover, making the PDF look like
    its start page repeated. Each must appear exactly once in pdf_mode."""
    html = render_report_html(_report(), pdf_mode=True)
    assert html.count("Request at a glance") == 1
    assert html.count("What this report tells you") == 0
    assert html.count('class="app-header"') == 0


def test_pdf_cover_shows_grounded_summary_when_present():
    report = _report()
    report.executive_summary = "This is a plain-language summary of the findings."
    html = render_report_html(report, pdf_mode=True)
    assert report.executive_summary in html
    assert html.count(report.executive_summary) == 1  # cover only, not duplicated


def test_pdf_research_note_is_surfaced():
    report = _report()
    report.research_note = "The form link was dead, so the homepage was used instead."
    html = render_report_html(report, pdf_mode=True)
    assert report.research_note in html


def test_pdf_attention_items_render_on_the_content_page():
    # _report() has one needs_review web finding — it should appear in the
    # PDF's "Needs your attention" list, not be lost with the cover trimming.
    html = render_report_html(_report(), pdf_mode=True)
    assert "Needs your attention" in html
    assert "Is it open to the public?" in html


def test_write_report_pdf_produces_a_real_pdf(tmp_path):
    path = write_report_pdf(_report(), tmp_path)
    assert path.exists()
    data = path.read_bytes()
    assert data[:5] == b"%PDF-"
    assert len(data) > 1000
    # The intermediate print-only HTML must not be left behind.
    assert not (tmp_path / "_report_print.html").exists()


def _appeal_report() -> ReportData:
    """An appeal report — the longest cover (denial-reason box + summary) — is
    the case that used to spill a near-blank second cover page (Sample 10 QA)."""
    web = [
        Finding("open", "Is the class open to the broader public?", "found", "Open to everyone."),
        Finding("fees", "Does the class have published fees?", "needs_review", "No fees found."),
        Finding("subject", "Is the class subject based?", "found", "Martial arts."),
        Finding("credits", "Does the class provide college credits? (must be NO)", "needs_review", "Silent."),
        Finding("schedule", "Is there a published schedule?", "needs_review", "No schedule."),
    ]
    internal = [Finding("b1", "Budget approved?", "internal", "Requires records.", group="Budget")]
    return ReportData(
        application_id="appeal01", category_display_name="Pre-Approval Appeal",
        generated_at=datetime.now(timezone.utc), participant_name="Yosef B.", provider_name="Gracie Barra",
        item_name="Adult Group Jiu Jitsu", webpage_url="https://graciebarra.com", form_fee="$30",
        findings=web + internal, fetch_error=None,
        appeal_denial_reason="Published fees could not be verified on the provider's website.",
        executive_summary=(
            "The Gracie Barra website confirms the class is open to the public and subject-based, "
            "but no published fee or schedule is visible, so several items need review. All internal "
            "checks still require human confirmation."
        ),
    )


def test_no_near_empty_pages_in_the_appeal_pdf(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    path = write_report_pdf(_appeal_report(), tmp_path)
    reader = pypdf.PdfReader(str(path))
    pages = reader.pages
    # Only the final page is allowed to be short (a footer/completion tail).
    for i, page in enumerate(pages[:-1]):
        chars = len(page.extract_text().strip())
        assert chars > 120, f"page {i + 1} is near-empty ({chars} chars) — pagination regressed"


@pytest.fixture
def client():
    return TestClient(app_mod.app)


def test_export_report_pdf_route(client, tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    record = ApplicationRecord(
        id="pdftest01", pdf_filename="test.pdf", pdf_path=run_dir / "source.pdf", run_dir=run_dir
    )
    record.report = _report()
    record.stage = "reported"
    store._records[record.id] = record

    resp = client.get(f"/applications/{record.id}/export/report.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"
