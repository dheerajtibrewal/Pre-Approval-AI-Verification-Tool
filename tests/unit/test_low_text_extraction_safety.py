"""Safe degradation on scanned / rotated / low-text PDFs.

We deliberately do NOT ship an OCR pipeline (out of scope — see
docs/limitations-and-assumptions.md). What we DO guarantee: an unreadable form
never passes through as if it were read cleanly. It is flagged loudly and every
field is marked low-confidence for reviewer correction, so nothing gets
fabricated silently. The LLM call is mocked — no network.
"""

from unittest.mock import patch

from preapproval_tool.checklist_engine.models import ChecklistConfig, Criterion, FormField
from preapproval_tool.extraction.field_extractor import extract_fields
from preapproval_tool.extraction.pdf_text import PdfText


def _checklist() -> ChecklistConfig:
    return ChecklistConfig(
        category_id="c", display_name="C", form_template_signature=["X"],
        item_name_field="item", fee_field=None,
        fields=[
            FormField(id="participant_name", label="Name", type="string"),
            FormField(id="item", label="Item", type="string"),
            FormField(id="webpage_url", label="URL", type="url"),
        ],
        criteria=[Criterion(id="r", question="Q?", verifiable="internal", check_type="rule")],
    )


def test_has_text_layer_is_false_for_a_near_empty_scan():
    scanned = PdfText(full_text="   \n  ", pages=["", ""], page_count=2)
    assert scanned.has_text_layer is False


def test_low_text_pdf_flags_every_field_and_warns_instead_of_trusting_the_guess():
    scanned = PdfText(full_text="", pages=[""], page_count=1)
    # Even if the model returns confident-looking values, a no-text-layer form
    # means they're guesses — all must be flagged for reviewer confirmation.
    fake_llm = {
        "participant_name": "Guessed Name", "item": "Guessed Item",
        "webpage_url": "https://guess.example", "low_confidence_fields": [],
    }
    with patch(
        "preapproval_tool.extraction.field_extractor.structured_completion",
        return_value=dict(fake_llm),
    ):
        extracted = extract_fields(_checklist(), scanned)

    assert extracted.warnings, "a scanned/low-text PDF must produce a warning"
    assert "scanned" in extracted.warnings[0].lower() or "readable text" in extracted.warnings[0].lower()
    # Every field flagged — nothing passes through as a clean reading.
    for fid in ("participant_name", "item", "webpage_url"):
        assert fid in extracted.low_confidence_fields


def test_normal_text_pdf_does_not_blanket_flag_fields():
    good = PdfText(
        full_text="Participant's Name: Jane Doe. Provider webpage: https://ex.org. " * 3,
        pages=["..."], page_count=1,
    )
    with patch(
        "preapproval_tool.extraction.field_extractor.structured_completion",
        return_value={
            "participant_name": "Jane Doe", "item": "Class", "webpage_url": "https://ex.org",
            "low_confidence_fields": [],
        },
    ):
        extracted = extract_fields(_checklist(), good)
    assert extracted.low_confidence_fields == []
    assert extracted.warnings == []
