from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from preapproval_tool.evidence.models import EvidenceItem

FindingStatus = Literal["found", "not_found", "needs_review", "internal"]


@dataclass
class ReviewEvent:
    """One audit-trail entry for a reviewer action on a finding."""

    action: str  # "override" | "mark_reviewed" | "restore"
    status: FindingStatus
    note: str
    at: str  # ISO timestamp


@dataclass
class Finding:
    criterion_id: str
    question: str
    status: FindingStatus
    note: str
    short_note: str = ""
    quoted_snippet: str | None = None
    evidence: list[EvidenceItem] = field(default_factory=list)
    reviewer_overridden: bool = False
    reviewed: bool = False
    original_status: FindingStatus | None = None
    original_note: str | None = None
    original_short_note: str | None = None
    history: list[ReviewEvent] = field(default_factory=list)
    group: str = ""
    form_answer: str | None = None  # "yes" | "no" | None — the applicant's own checked answer
    confidence: str | None = None  # "high" | "medium" | "low" | None (non-LLM check types)

    def apply_reviewer_override(self, *, status: FindingStatus, note: str) -> None:
        if not self.reviewer_overridden:
            self.original_status = self.status
            self.original_note = self.note
            self.original_short_note = self.short_note
        self.status = status
        self.note = note
        # The system-generated short_note no longer reflects reality once a
        # reviewer overrides the note — clear it so display_short_note falls
        # back to (a truncation of) the reviewer's own note instead of
        # silently showing a stale, LLM-written summary in the collapsed view.
        self.short_note = ""
        self.reviewer_overridden = True
        self.reviewed = True
        self.history.append(
            ReviewEvent(
                action="override",
                status=status,
                note=note,
                at=datetime.now(timezone.utc).isoformat(),
            )
        )

    def mark_reviewed(self) -> None:
        """Reviewer confirms the system's finding as-is, without changing it."""
        self.reviewed = True
        self.history.append(
            ReviewEvent(
                action="mark_reviewed",
                status=self.status,
                note=self.note,
                at=datetime.now(timezone.utc).isoformat(),
            )
        )

    def restore_system_result(self) -> None:
        if self.original_status is not None:
            self.status = self.original_status
            self.note = self.original_note or self.note
            self.short_note = self.original_short_note or ""
        self.reviewer_overridden = False
        self.reviewed = False
        self.history.append(
            ReviewEvent(
                action="restore",
                status=self.status,
                note=self.note,
                at=datetime.now(timezone.utc).isoformat(),
            )
        )

    @property
    def display_short_note(self) -> str:
        """A single-line conclusion for the collapsed card view. Falls back to
        a truncated version of the full note for findings that never went
        through an LLM judgment call (rule/exclusion-list/fee-match/internal),
        whose notes are already written to be short.
        """
        if self.short_note:
            return self.short_note
        return self.note if len(self.note) <= 140 else self.note[:137].rstrip() + "…"

    def __post_init__(self) -> None:
        # Hard invariant: a "found" status is meaningless — and per the brief,
        # an automatic-fail hallucination risk — unless it is backed by at
        # least one real evidence capture. Enforce it here, not just upstream.
        # This runs on every construction, including when a persisted review
        # is reapplied to a freshly re-evaluated Finding, so it can never be
        # bypassed by a stale reviewer override either.
        if self.status == "found" and not self.evidence:
            self.status = "needs_review"
            self.note = (
                f"{self.note} [Automatically downgraded from Found: no capturable "
                "evidence artifact was available for this finding.]"
            ).strip()
