from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

from preapproval_tool.evaluation.models import Finding


@dataclass
class ReportData:
    application_id: str
    category_display_name: str
    generated_at: datetime
    participant_name: str | None
    provider_name: str | None
    item_name: str | None
    webpage_url: str | None
    form_fee: str | None
    findings: list[Finding]
    fetch_error: str | None
    low_confidence_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    appeal_denial_reason: str | None = None
    published_fee_note: str | None = None
    last_updated: datetime | None = None
    research_note: str | None = None
    executive_summary: str | None = None

    @property
    def display_title(self) -> str:
        """Report headline. Usually "<item> — <provider>", but many forms (e.g.
        LaGuardia's transition program) list the provider AS the requested item,
        which produced a duplicated "X — X" header. Collapse to a single name
        when the two are effectively the same, and degrade gracefully when
        either is missing.
        """
        item = (self.item_name or "").strip()
        provider = (self.provider_name or "").strip()
        if item and provider:
            if item.casefold() == provider.casefold():
                return item
            return f"{item} — {provider}"
        return item or provider or "Requested item"

    @property
    def web_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.status != "internal"]

    @property
    def internal_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.status == "internal"]

    @property
    def summary_counts(self) -> dict[str, int]:
        counts = {"found": 0, "not_found": 0, "needs_review": 0}
        for f in self.web_findings:
            counts[f.status] = counts.get(f.status, 0) + 1
        return counts

    @property
    def source_domain(self) -> str | None:
        if not self.webpage_url:
            return None
        return urlparse(self.webpage_url).netloc or None

    @property
    def reviewed_count(self) -> int:
        return sum(1 for f in self.web_findings if f.reviewed)

    @property
    def total_reviewable(self) -> int:
        return len(self.web_findings)

    @property
    def internal_reviewed_count(self) -> int:
        return sum(1 for f in self.internal_findings if f.reviewed)

    @property
    def total_internal(self) -> int:
        return len(self.internal_findings)

    @property
    def overall_reviewed_count(self) -> int:
        return self.reviewed_count + self.internal_reviewed_count

    @property
    def overall_total(self) -> int:
        return self.total_reviewable + self.total_internal

    @property
    def unconfirmed_evidence_findings(self) -> list[Finding]:
        """Findings marked Confirmed that, for any reason, lack a real
        evidence capture — re-checked here (not just trusted from
        construction time) since this list drives the export gate."""
        return [f for f in self.web_findings if f.status == "found" and not f.evidence]

    @property
    def is_review_complete(self) -> bool:
        return (
            self.overall_reviewed_count == self.overall_total
            and not self.unconfirmed_evidence_findings
        )

    @property
    def all_evidence(self) -> list[tuple]:
        """Deduplicated (EvidenceItem, [criterion_ids]) pairs across every
        finding — the same whole-page capture is referenced by many findings,
        so the Evidence tab shows it once with all the findings it supports.
        """
        by_id: dict[str, list] = {}
        for f in self.findings:
            for e in f.evidence:
                if e.evidence_id not in by_id:
                    by_id[e.evidence_id] = [e, []]
                if f.criterion_id not in by_id[e.evidence_id][1]:
                    by_id[e.evidence_id][1].append(f.criterion_id)
        return [(e, ids) for e, ids in by_id.values()]

    @property
    def criterion_questions(self) -> dict[str, str]:
        return {f.criterion_id: f.question for f in self.findings}

    @property
    def attention_items(self) -> list[Finding]:
        """3-5 plain-language items the reviewer should look at first —
        anything not cleanly confirmed, prioritizing Not Found over Needs
        Review, surfaced on the Overview screen.
        """
        not_found = [f for f in self.web_findings if f.status == "not_found"]
        needs_review = [f for f in self.web_findings if f.status == "needs_review"]
        return (not_found + needs_review)[:5]
