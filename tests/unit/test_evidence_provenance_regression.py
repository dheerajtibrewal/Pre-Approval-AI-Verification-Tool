"""Fixture-locked regression coverage for the evidence-provenance invariant
exercised live by Sample 10 (the Gracie Barra appeal): an LLM's "found"
verdict is worthless — and per the brief, an automatic-fail hallucination
risk — unless its supporting quote actually appears in the page content that
was really captured. This test locks that invariant in at the full
run_evaluation() level (not just the is_quote_grounded() primitive covered
in test_text_utils.py), so a future refactor of evaluator.py can't silently
drop the check. No LLM/network calls — judge_criterion is mocked to return
exactly what a hallucinating model would.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone

import pytest
from PIL import Image

import preapproval_tool.evaluation.evaluator as evaluator_mod
import preapproval_tool.evidence.capture_service as capture_service_mod
from preapproval_tool.checklist_engine.models import ChecklistConfig, Criterion, FormField
from preapproval_tool.extraction.models import ExtractedApplication
from preapproval_tool.research.models import FetchAttempt, FetchResult, PageCapture


def _tiny_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), (255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _no_real_screenshots(monkeypatch):
    monkeypatch.setattr(capture_service_mod, "screenshot_element_by_text", lambda *a, **k: None)


def test_fabricated_quote_is_discarded_and_finding_held_at_needs_review(tmp_path, monkeypatch):
    criterion = Criterion(
        id="published_fees",
        question="Does the class have published fees?",
        verifiable="web",
        check_type="llm_judgment",
    )
    checklist = ChecklistConfig(
        category_id="test-category",
        display_name="Test Category",
        form_template_signature=["Test Form"],
        item_name_field="item_name",
        fee_field=None,
        fields=[FormField(id="item_name", label="Item", type="string")],
        criteria=[criterion],
    )
    real_page_text = "Gracie Barra offers Jiu-Jitsu classes for all ages."
    capture = PageCapture(
        url="https://graciebarra.com",
        final_url="https://graciebarra.com",
        text_content=real_page_text,
        screenshot_bytes=_tiny_png(),
        fetched_at=datetime.now(timezone.utc),
        method="firecrawl",
        page_title="Gracie Barra",
    )
    fetch_result = FetchResult(
        url=capture.url, capture=capture, attempts=[FetchAttempt("firecrawl", True)]
    )

    # A hallucinating model: confidently "found", but the quote it cites was
    # never actually on the captured page — exactly the automatic-fail risk
    # the brief names by name.
    def fake_judge(criterion, *, page_text, form_context):
        return {
            "status": "found",
            "confidence": "high",
            "short_note": "Fees are published at $30 per class.",
            "note": "The website clearly lists the class fee.",
            "quoted_snippet": "Adult classes are $30 per session, billed monthly.",
        }

    monkeypatch.setattr(evaluator_mod, "judge_criterion", fake_judge)
    monkeypatch.setattr(evaluator_mod, "fetch_page", lambda url: fetch_result)

    capture_service = capture_service_mod.EvidenceCaptureService(tmp_path)
    extracted = ExtractedApplication(
        category_id="test-category",
        values={"webpage_url": "https://graciebarra.com", "item_name": "Adult Group Jiu Jitsu"},
    )
    run = evaluator_mod.run_evaluation(checklist, extracted, capture_service)

    finding = next(f for f in run.findings if f.criterion_id == "published_fees")
    assert finding.status == "needs_review"
    assert finding.quoted_snippet is None
    assert "could not be verified against the captured page content" in finding.note
