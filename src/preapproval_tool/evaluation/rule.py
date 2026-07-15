"""check_type == "rule": used for internal/document criteria. No web check is
attempted — these are, by the brief's own design, out of the website's reach.
"""

from __future__ import annotations

from preapproval_tool.checklist_engine.models import Criterion


def evaluate_rule(criterion: Criterion) -> dict[str, str | None]:
    if criterion.explanation:
        note = criterion.explanation
    elif criterion.verifiable == "document":
        note = (
            "Needs supporting document — this can only be verified from an "
            "uploaded letter/attachment, not the provider's website."
        )
    else:
        note = (
            "Internal — depends on the participant's budget, Life Plan, or "
            "other back-office data the tool does not have access to. Not "
            "guessed; left for reviewer confirmation."
        )
    return {"status": "internal", "note": note, "quoted_snippet": None}
