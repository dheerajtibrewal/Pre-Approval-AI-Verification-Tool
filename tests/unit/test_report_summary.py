"""The executive summary is the one spot LLM prose enters the report body, so
it must be grounded (fed only computed findings) and strictly optional — a
failed call returns None and the report falls back to its templated line."""

from datetime import datetime, timezone
from unittest.mock import patch

from preapproval_tool.evaluation.models import Finding
from preapproval_tool.report import summary as summary_mod
from preapproval_tool.report.models import ReportData


def _report() -> ReportData:
    return ReportData(
        application_id="x1",
        category_display_name="Membership",
        generated_at=datetime.now(timezone.utc),
        participant_name="P.",
        provider_name="Planet Fitness",
        item_name="Classic Gym Membership",
        webpage_url="https://example.org",
        form_fee="$15",
        findings=[
            Finding("open", "Open to the public?", "found", "Yes, join now.", form_answer="yes"),
            Finding("fee", "Fee published?", "needs_review", "Price varies by location.", form_answer=None),
        ],
        fetch_error=None,
    )


def test_returns_grounded_summary_on_success():
    with patch.object(summary_mod, "structured_completion", return_value={"summary": "Open to public; price needs review."}) as mock:
        result = summary_mod.generate_executive_summary(_report())
    assert result == "Open to public; price needs review."
    # The findings — not raw website text — are what's sent to the model.
    sent = mock.call_args.kwargs["user_prompt"]
    assert "Price varies by location." in sent
    assert "Planet Fitness" in sent


def test_returns_none_on_llm_failure():
    with patch.object(summary_mod, "structured_completion", side_effect=RuntimeError("down")):
        assert summary_mod.generate_executive_summary(_report()) is None


def test_returns_none_when_no_web_findings():
    report = _report()
    report.findings = [Finding("b", "Budget approved?", "internal", "Needs record.", group="Budget")]
    with patch.object(summary_mod, "structured_completion", side_effect=AssertionError("should not call")):
        assert summary_mod.generate_executive_summary(report) is None
