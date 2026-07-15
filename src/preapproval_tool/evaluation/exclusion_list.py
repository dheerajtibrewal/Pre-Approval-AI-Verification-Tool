"""exclusion_list check_type: a deterministic keyword-overlap gate against the
category's configured exclusion list (config/checklists/*.yaml `exclusion_list`).

This is intentionally NOT an LLM call. Per the brief's "no guessing on the
checklist" rule and the Sample 07 (laptop → "Computer Hardware") test case,
whether an item is excluded must be a reproducible, auditable rule, not an
emergent LLM judgment — false negatives here (missing an excluded item) are
the single worst failure mode this system can have.

The heuristic is deliberately conservative in the other direction: it only
flags a *possible* match for the reviewer, worded as "plausibly excluded",
never as a final determination — a human still confirms.
"""

from __future__ import annotations

import re

from preapproval_tool.checklist_engine.models import Criterion

_STOPWORDS = {"and", "the", "for", "or", "with", "a", "an", "of", "to", "in"}
_MIN_TOKEN_LEN = 4


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z]+", text.lower())
    return {w for w in words if len(w) >= _MIN_TOKEN_LEN and w not in _STOPWORDS}


def evaluate_exclusion_list(criterion: Criterion, *, item_name: str) -> dict[str, str | None]:
    item_tokens = _tokens(item_name)
    for term in criterion.exclusion_list:
        term_tokens = _tokens(term)
        overlap = item_tokens & term_tokens
        if overlap:
            return {
                "status": "not_found",
                "note": (
                    f"'{item_name}' shares term(s) {sorted(overlap)} with the "
                    f"exclusion-list entry '{term}'. This is a deterministic "
                    "keyword match, not a final determination — reviewer must "
                    "confirm whether this item is actually excluded."
                ),
                "quoted_snippet": None,
            }
    return {
        "status": "found",
        "note": (
            f"No overlap found between '{item_name}' and the configured "
            "exclusion list. This supports (but does not by itself prove) "
            "that the item is not excluded."
        ),
        "quoted_snippet": None,
    }
