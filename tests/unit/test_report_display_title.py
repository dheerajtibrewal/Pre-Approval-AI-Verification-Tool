"""Report headline de-duplication.

Regression (Sample 09 LaGuardia): several forms list the provider AS the
requested item, so the "<item> — <provider>" headline rendered "X — X". The
`display_title` property collapses that to a single name and degrades gracefully
when either field is missing.
"""

from datetime import datetime, timezone

from preapproval_tool.report.models import ReportData


def _report(item, provider) -> ReportData:
    return ReportData(
        application_id="t", category_display_name="C",
        generated_at=datetime.now(timezone.utc),
        participant_name="P", provider_name=provider, item_name=item,
        webpage_url=None, form_fee=None, findings=[], fetch_error=None,
    )


def test_identical_item_and_provider_collapse_to_one_name():
    r = _report("LaGuardia Community College", "LaGuardia Community College")
    assert r.display_title == "LaGuardia Community College"


def test_case_insensitive_dedup():
    assert _report("Planet Fitness", "planet fitness").display_title == "Planet Fitness"


def test_distinct_names_are_joined():
    assert _report("Classic Membership", "Planet Fitness").display_title == "Classic Membership — Planet Fitness"


def test_missing_provider_uses_item_only():
    assert _report("Grab Bar", None).display_title == "Grab Bar"


def test_missing_item_uses_provider_only():
    assert _report(None, "Gracie Barra").display_title == "Gracie Barra"


def test_both_missing_falls_back():
    assert _report(None, None).display_title == "Requested item"
