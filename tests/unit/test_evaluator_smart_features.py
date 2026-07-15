"""Tests for the two "smarter system" behaviors added after user QA:
confidence-gated self-consistency re-checking, and the bounded subpage
rescue fetch. Everything is mocked — no real OpenAI/Firecrawl/Playwright
calls — so these are fast and deterministic.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone

import pytest
from PIL import Image

from preapproval_tool.checklist_engine.models import ChecklistConfig, Criterion, FormField
from preapproval_tool.extraction.models import ExtractedApplication
from preapproval_tool.research.models import FetchAttempt, FetchResult, PageCapture

import preapproval_tool.evaluation.evaluator as evaluator_mod
import preapproval_tool.evidence.capture_service as capture_service_mod


def _tiny_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), (255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _checklist(criteria: list[Criterion]) -> ChecklistConfig:
    return ChecklistConfig(
        category_id="test-category",
        display_name="Test Category",
        form_template_signature=["Test Form"],
        item_name_field="item_name",
        fee_field=None,
        fields=[FormField(id="item_name", label="Item", type="string")],
        criteria=criteria,
    )


def _extracted() -> ExtractedApplication:
    return ExtractedApplication(
        category_id="test-category",
        values={"webpage_url": "https://example.org", "item_name": "Test Class"},
    )


def _capture(text: str, links: list[str] | None = None, url: str = "https://example.org") -> PageCapture:
    return PageCapture(
        url=url,
        final_url=url,
        text_content=text,
        screenshot_bytes=_tiny_png(),
        fetched_at=datetime.now(timezone.utc),
        method="firecrawl",
        page_title="Test Page",
        links=links or [],
    )


@pytest.fixture(autouse=True)
def _fake_targeted_screenshots(monkeypatch):
    # capture_targeted() locates text via a real Playwright call — short-circuit
    # it so these tests never touch the network. Return real PNG bytes so a
    # targeted crop is produced by default (a Found needs a readable targeted
    # crop to survive — see the point-4 rule; tests that specifically exercise
    # the "no crop -> downgrade" path override this to return None).
    monkeypatch.setattr(
        capture_service_mod, "screenshot_element_by_text", lambda *a, **k: _tiny_png()
    )


def test_confidence_gated_recheck_holds_at_needs_review_on_disagreement(tmp_path, monkeypatch):
    criterion = Criterion(
        id="open_to_public",
        question="Is it open to the public?",
        verifiable="web",
        check_type="llm_judgment",
    )
    checklist = _checklist([criterion])
    capture = _capture("Some ambiguous page text.")
    fetch_result = FetchResult(url=capture.url, capture=capture, attempts=[FetchAttempt("firecrawl", True)])

    calls = {"n": 0}

    def fake_judge(criterion, *, page_text, form_context):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "status": "found", "confidence": "low", "short_note": "Seems open.",
                "note": "The page seems to suggest this.", "quoted_snippet": None,
            }
        return {
            "status": "not_found", "confidence": "medium", "short_note": "Actually not.",
            "note": "On second look, it does not.", "quoted_snippet": None,
        }

    monkeypatch.setattr(evaluator_mod, "judge_criterion", fake_judge)
    monkeypatch.setattr(evaluator_mod, "fetch_page", lambda url: fetch_result)

    capture_service = capture_service_mod.EvidenceCaptureService(tmp_path)
    run = evaluator_mod.run_evaluation(checklist, _extracted(), capture_service)

    assert calls["n"] == 2  # the re-check actually happened
    finding = next(f for f in run.findings if f.criterion_id == "open_to_public")
    assert finding.status == "needs_review"
    assert "independently re-checked" in finding.note


def test_confidence_gated_recheck_keeps_result_when_consistent(tmp_path, monkeypatch):
    criterion = Criterion(
        id="open_to_public",
        question="Is it open to the public?",
        verifiable="web",
        check_type="llm_judgment",
    )
    checklist = _checklist([criterion])
    capture = _capture("Open to everyone, quote: 'we welcome the public'.")
    fetch_result = FetchResult(url=capture.url, capture=capture, attempts=[FetchAttempt("firecrawl", True)])

    def fake_judge(criterion, *, page_text, form_context):
        return {
            "status": "found", "confidence": "low", "short_note": "Open to public.",
            "note": "Clearly open.", "quoted_snippet": "we welcome the public",
        }

    monkeypatch.setattr(evaluator_mod, "judge_criterion", fake_judge)
    monkeypatch.setattr(evaluator_mod, "fetch_page", lambda url: fetch_result)

    capture_service = capture_service_mod.EvidenceCaptureService(tmp_path)
    run = evaluator_mod.run_evaluation(checklist, _extracted(), capture_service)

    finding = next(f for f in run.findings if f.criterion_id == "open_to_public")
    assert finding.status == "found"
    assert "double-checked due to low confidence" in finding.note


def test_subpage_rescue_resolves_a_fee_criterion_from_a_linked_pricing_page(tmp_path, monkeypatch):
    criterion = Criterion(
        id="published_fees",
        question="Does the class have published fees?",
        verifiable="web",
        check_type="llm_judgment",
        evidence_label="Evidence: published fees",
    )
    checklist = _checklist([criterion])
    homepage = _capture(
        "Welcome to our gym.",
        links=["https://example.org/", "https://example.org/pricing"],
    )
    fetch_result = FetchResult(url=homepage.url, capture=homepage, attempts=[FetchAttempt("firecrawl", True)])
    pricing_page = _capture(
        "Group classes are $25 per session.", url="https://example.org/pricing"
    )

    def fake_judge(criterion, *, page_text, form_context):
        if "ADDITIONAL PAGE CHECKED" in page_text and "$25" in page_text:
            return {
                "status": "found", "confidence": "high", "short_note": "Fee published.",
                "note": "The pricing page lists $25 per session.",
                "quoted_snippet": "Group classes are $25 per session.",
            }
        return {
            "status": "needs_review", "confidence": "high", "short_note": "No fee visible.",
            "note": "The homepage does not mention fees.", "quoted_snippet": None,
        }

    def fake_fetch_page(url):
        if url == "https://example.org/pricing":
            return FetchResult(url=url, capture=pricing_page, attempts=[FetchAttempt("firecrawl", True)])
        return fetch_result

    monkeypatch.setattr(evaluator_mod, "judge_criterion", fake_judge)
    monkeypatch.setattr(evaluator_mod, "fetch_page", fake_fetch_page)
    # Force the deterministic keyword fallback so this test never makes a real
    # LLM link-ranking call.
    monkeypatch.setattr(evaluator_mod, "rank_links", lambda *a, **k: None)

    capture_service = capture_service_mod.EvidenceCaptureService(tmp_path)
    run = evaluator_mod.run_evaluation(checklist, _extracted(), capture_service)

    finding = next(f for f in run.findings if f.criterion_id == "published_fees")
    assert finding.status == "found"
    assert "Resolved after checking a linked page" in finding.note
    assert finding.evidence  # got real evidence, not left empty


def test_subpage_rescue_does_not_run_when_nothing_needs_help(tmp_path, monkeypatch):
    criterion = Criterion(
        id="published_fees",
        question="Does the class have published fees?",
        verifiable="web",
        check_type="llm_judgment",
    )
    checklist = _checklist([criterion])
    homepage = _capture(
        "Classes cost $25 per session.",
        links=["https://example.org/pricing"],
    )
    fetch_result = FetchResult(url=homepage.url, capture=homepage, attempts=[FetchAttempt("firecrawl", True)])

    fetch_calls = {"n": 0}

    def fake_fetch_page(url):
        fetch_calls["n"] += 1
        return fetch_result

    def fake_judge(criterion, *, page_text, form_context):
        return {
            "status": "found", "confidence": "high", "short_note": "Fee found.",
            "note": "Costs $25.", "quoted_snippet": "Classes cost $25 per session.",
        }

    monkeypatch.setattr(evaluator_mod, "judge_criterion", fake_judge)
    monkeypatch.setattr(evaluator_mod, "fetch_page", fake_fetch_page)
    monkeypatch.setattr(evaluator_mod, "rank_links", lambda *a, **k: None)

    capture_service = capture_service_mod.EvidenceCaptureService(tmp_path)
    evaluator_mod.run_evaluation(checklist, _extracted(), capture_service)

    assert fetch_calls["n"] == 1  # only the original fetch — no subpage rescue triggered


def test_website_found_without_a_targeted_crop_is_downgraded(tmp_path, monkeypatch):
    """Point 4 (PM QA): a website 'Found' that can't be backed by a readable
    targeted crop — e.g. the absence-based 'no college credit' Found off a
    silent page — must not stand as Confirmed. Here the crop fails (returns
    None), so an otherwise-'found' llm_judgment is held at Needs Review."""
    criterion = Criterion(
        id="college_credits", question="Does the class provide college credits? (must be NO)",
        verifiable="web", check_type="llm_judgment",
    )
    checklist = _checklist([criterion])
    capture = _capture("The class focuses on discipline and personal growth.")
    fetch_result = FetchResult(url=capture.url, capture=capture, attempts=[FetchAttempt("firecrawl", True)])

    def fake_judge(criterion, *, page_text, form_context):
        return {"status": "found", "confidence": "high", "short_note": "No credits mentioned.",
                "note": "The page does not mention college credits.", "quoted_snippet": None}

    monkeypatch.setattr(evaluator_mod, "judge_criterion", fake_judge)
    monkeypatch.setattr(evaluator_mod, "fetch_page", lambda url: fetch_result)
    monkeypatch.setattr(evaluator_mod, "rank_links", lambda *a, **k: None)
    # No targeted crop can be produced.
    monkeypatch.setattr(capture_service_mod, "screenshot_element_by_text", lambda *a, **k: None)

    capture_service = capture_service_mod.EvidenceCaptureService(tmp_path)
    run = evaluator_mod.run_evaluation(checklist, _extracted(), capture_service)
    finding = next(f for f in run.findings if f.criterion_id == "college_credits")
    assert finding.status == "needs_review"
    assert "targeted screenshot" in finding.note


def test_exclusion_list_found_is_exempt_from_the_targeted_crop_rule(tmp_path, monkeypatch):
    """A deterministic exclusion-list 'Found' (item NOT on the list) carries its
    own configured rule provenance and needs no screenshot — it must not be
    downgraded by the targeted-evidence rule even with no crop available."""
    criterion = Criterion(
        id="exclusion_check", question="Is the item on the exclusion list? (must be NO)",
        verifiable="web", check_type="exclusion_list", exclusion_list=["Cable TV"],
    )
    checklist = _checklist([criterion])
    checklist.item_name_field = "item_name"
    capture = _capture("Some product page.")
    fetch_result = FetchResult(url=capture.url, capture=capture, attempts=[FetchAttempt("firecrawl", True)])

    monkeypatch.setattr(evaluator_mod, "fetch_page", lambda url: fetch_result)
    monkeypatch.setattr(evaluator_mod, "rank_links", lambda *a, **k: None)
    monkeypatch.setattr(capture_service_mod, "screenshot_element_by_text", lambda *a, **k: None)

    capture_service = capture_service_mod.EvidenceCaptureService(tmp_path)
    run = evaluator_mod.run_evaluation(
        _checklist([criterion]), _extracted(), capture_service
    )
    finding = next(f for f in run.findings if f.criterion_id == "exclusion_check")
    assert finding.status == "found"  # item "Test Class" not on the list; stays Found


def test_blocked_page_reports_honestly_and_skips_llm(tmp_path, monkeypatch):
    """A CAPTCHA/anti-bot wall must be reported as blocked, not fed to the LLM
    (which described Amazon's bot check as a 'general navigation page')."""
    criterion = Criterion(
        id="item_visible", question="Does the linked page show the item with a price?",
        verifiable="web", check_type="llm_judgment",
    )
    checklist = _checklist([criterion])
    blocked = _capture("Click the button below to continue shopping", url="https://www.amazon.com/dp/X")
    fetch_result = FetchResult(url=blocked.url, capture=blocked, attempts=[FetchAttempt("playwright", True)])

    def fake_judge(*a, **k):
        raise AssertionError("LLM must not be called on a blocked page")

    monkeypatch.setattr(evaluator_mod, "judge_criterion", fake_judge)
    monkeypatch.setattr(evaluator_mod, "fetch_page", lambda url: fetch_result)
    monkeypatch.setattr(evaluator_mod, "rank_links", lambda *a, **k: None)

    capture_service = capture_service_mod.EvidenceCaptureService(tmp_path)
    run = evaluator_mod.run_evaluation(checklist, _extracted(), capture_service)
    finding = next(f for f in run.findings if f.criterion_id == "item_visible")
    assert finding.status == "needs_review"
    assert "blocked automated access" in finding.note
    assert run.research_note and "blocked automated access" in run.research_note


def test_navigator_follows_two_hops_to_reach_a_deep_pricing_page(tmp_path, monkeypatch):
    """Homepage → a 'gyms' index → a specific club's offers page: the price
    lives two links deep, and the bounded navigator must reach it."""
    criterion = Criterion(
        id="published_fees",
        question="Does the organization publish membership fees?",
        verifiable="web",
        check_type="llm_judgment",
        evidence_label="Evidence: published fees",
    )
    checklist = _checklist([criterion])
    homepage = _capture("Welcome.", links=["https://example.org/gyms"], url="https://example.org")
    gyms = _capture("Find a club.", links=["https://example.org/gyms/salina/offers"], url="https://example.org/gyms")
    offers = _capture("CLASSIC $15 /mo plus taxes.", url="https://example.org/gyms/salina/offers")
    by_url = {
        "https://example.org": homepage,
        "https://example.org/gyms": gyms,
        "https://example.org/gyms/salina/offers": offers,
    }

    def fake_fetch_page(url):
        cap = by_url.get(url.rstrip("/")) or by_url.get(url) or homepage
        return FetchResult(url=url, capture=cap, attempts=[FetchAttempt("firecrawl", True)])

    def fake_judge(criterion, *, page_text, form_context):
        if "$15" in page_text:
            return {"status": "found", "confidence": "high", "short_note": "Fee found.",
                    "note": "Lists $15/mo.", "quoted_snippet": "CLASSIC $15 /mo plus taxes."}
        return {"status": "needs_review", "confidence": "high", "short_note": "No fee.",
                "note": "No fee here.", "quoted_snippet": None}

    # Steer the navigator deterministically: follow whatever same-site links exist.
    monkeypatch.setattr(evaluator_mod, "judge_criterion", fake_judge)
    monkeypatch.setattr(evaluator_mod, "fetch_page", fake_fetch_page)
    monkeypatch.setattr(evaluator_mod, "rank_links", lambda q, candidates, limit=2: candidates[:limit])

    capture_service = capture_service_mod.EvidenceCaptureService(tmp_path)
    run = evaluator_mod.run_evaluation(checklist, _extracted(), capture_service)

    finding = next(f for f in run.findings if f.criterion_id == "published_fees")
    assert finding.status == "found"
    assert "Resolved after checking a linked page" in finding.note


def test_navigator_recovers_when_the_form_url_itself_is_dead(tmp_path, monkeypatch):
    """A stale form link that 404s must not sink the whole report: the tool
    backs off to the site homepage, records that it did, and can still find
    the price from there."""
    criterion = Criterion(
        id="published_fees",
        question="Does the organization publish membership fees?",
        verifiable="web",
        check_type="llm_judgment",
        evidence_label="Evidence: published fees",
    )
    checklist = _checklist([criterion])
    extracted = ExtractedApplication(
        category_id="test-category",
        values={"webpage_url": "https://example.org/join", "item_name": "Membership"},
    )
    homepage = _capture("Home.", links=["https://example.org/membership"], url="https://example.org/")
    membership = _capture("Individual membership is $80 a year.", url="https://example.org/membership")

    def fake_fetch_page(url):
        if url.rstrip("/") == "https://example.org/join":
            return FetchResult(url=url, capture=None, attempts=[FetchAttempt("firecrawl", False, "HTTP 404")])
        if url.rstrip("/") in ("https://example.org", "https://example.org"):
            return FetchResult(url=url, capture=homepage, attempts=[FetchAttempt("firecrawl", True)])
        if url == "https://example.org/membership":
            return FetchResult(url=url, capture=membership, attempts=[FetchAttempt("firecrawl", True)])
        return FetchResult(url=url, capture=homepage, attempts=[FetchAttempt("firecrawl", True)])

    def fake_judge(criterion, *, page_text, form_context):
        if "$80" in page_text:
            return {"status": "found", "confidence": "high", "short_note": "Fee found.",
                    "note": "Lists $80/year.", "quoted_snippet": "Individual membership is $80 a year."}
        return {"status": "needs_review", "confidence": "high", "short_note": "No fee.",
                "note": "No fee here.", "quoted_snippet": None}

    monkeypatch.setattr(evaluator_mod, "judge_criterion", fake_judge)
    monkeypatch.setattr(evaluator_mod, "fetch_page", fake_fetch_page)
    monkeypatch.setattr(evaluator_mod, "rank_links", lambda q, candidates, limit=2: candidates[:limit])

    capture_service = capture_service_mod.EvidenceCaptureService(tmp_path)
    run = evaluator_mod.run_evaluation(checklist, extracted, capture_service)

    assert run.research_note is not None
    assert "main website" in run.research_note
    finding = next(f for f in run.findings if f.criterion_id == "published_fees")
    assert finding.status == "found"
