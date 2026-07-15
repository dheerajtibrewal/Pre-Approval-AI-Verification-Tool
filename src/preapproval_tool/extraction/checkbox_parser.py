"""Parses the applicant's own YES/NO checkbox answers from the PDF text layer.

The forms render checked/unchecked boxes as the glyphs ☑ / ☐, always in a
YES-then-NO column order immediately after the question text (confirmed by
inspecting the real sample PDFs' extracted text). This lets the report show
"Application answer: Yes" next to the tool's own website-verification result
— a plain-language comparison, not just our own finding in isolation.

Deliberately regex/string-based, not an LLM call: this is reading a fixed,
known form layout, not interpreting free text.
"""

from __future__ import annotations

import re

from preapproval_tool.checklist_engine.models import Criterion

_CHECKBOX_GLYPHS = ("☑", "☐")
_LOOKAHEAD_CHARS = 80


_QUOTE_MAP = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_QUOTE_MAP)).strip()


def parse_checkbox_answers(raw_text: str, criteria: list[Criterion]) -> dict[str, str | None]:
    normalized_text = _normalize(raw_text)
    answers: dict[str, str | None] = {}

    for criterion in criteria:
        question = _normalize(criterion.form_question_text).rstrip("?")
        if not question:
            answers[criterion.id] = None
            continue

        idx = normalized_text.find(question)
        if idx == -1:
            idx = normalized_text.lower().find(question.lower())
        if idx == -1:
            answers[criterion.id] = None
            continue

        tail = normalized_text[idx + len(question) : idx + len(question) + _LOOKAHEAD_CHARS]
        glyphs = [ch for ch in tail if ch in _CHECKBOX_GLYPHS]
        if len(glyphs) < 2:
            answers[criterion.id] = None
            continue

        yes_glyph, no_glyph = glyphs[0], glyphs[1]
        if yes_glyph == "☑" and no_glyph != "☑":
            answers[criterion.id] = "yes"
        elif no_glyph == "☑" and yes_glyph != "☑":
            answers[criterion.id] = "no"
        else:
            answers[criterion.id] = None  # ambiguous/ocr-noisy — don't guess

    return answers
