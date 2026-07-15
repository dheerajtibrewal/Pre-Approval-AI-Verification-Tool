"""Text-cleaning and evidence-grounding helpers shared by the evaluator.

Firecrawl returns page content as markdown, so raw LLM quotes can carry
markdown syntax (`**bold**`, `# heading`, `[text](url)`) that looks like a
rendering bug when shown verbatim in the report. Stripping it is purely
cosmetic for display; grounding checks compare against the *stripped* form on
both sides so formatting differences don't cause false "ungrounded" flags.
"""

from __future__ import annotations

import re

_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_EMPHASIS = re.compile(r"(\*\*\*|\*\*|\*|___|__|_)")
_MD_HEADING = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_MD_CODE = re.compile(r"`+")
_WHITESPACE = re.compile(r"\s+")


def strip_markdown(text: str) -> str:
    text = _MD_LINK.sub(r"\1", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_CODE.sub("", text)
    text = _MD_EMPHASIS.sub("", text)
    return text.strip()


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", strip_markdown(text)).strip().lower()


def is_quote_grounded(quote: str, source_text: str) -> bool:
    """True if `quote` (modulo markdown/whitespace formatting) actually
    appears in `source_text` — the captured page content. This is the
    evidence-integrity check: an LLM must not get credit for a quote it
    invented rather than copied.
    """
    if not quote or not source_text:
        return False
    return _normalize(quote) in _normalize(source_text)
