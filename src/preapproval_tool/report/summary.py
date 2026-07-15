"""A short, plain-language executive summary for the top of the report.

This is the one place LLM prose enters the report body, so it is tightly
constrained: it is fed ONLY the already-computed findings (question + status +
the tool's own note) and the verdict counts — never the raw website text — and
is instructed to restate what the tool already concluded, not to add facts or
make a decision. If the call fails, the report simply omits it and falls back
to the existing deterministic summary line; it is never load-bearing.
"""

from __future__ import annotations

from preapproval_tool.llm.client import structured_completion
from preapproval_tool.report.models import ReportData

_SYSTEM_PROMPT = (
    "You write a 2-4 sentence plain-language summary at the top of a "
    "pre-approval website-verification report, for a busy non-technical "
    "reviewer. You are given the findings the tool already computed. Rules: "
    "restate only what the findings say — never introduce a fact, price, or "
    "detail not present in them. Never say the request is approved, denied, "
    "eligible, or ineligible; this tool only assists, a human decides. Lead "
    "with what was confirmed on the website, then what needs the reviewer's "
    "attention and briefly why, then note that the Internal Checks always "
    "need human confirmation. Be calm, concrete, and specific to THIS "
    "provider and these findings — not generic boilerplate. No bullet points, "
    "no headings, just the sentences."
)

_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
    "additionalProperties": False,
}


def generate_executive_summary(report: ReportData) -> str | None:
    """Returns a grounded plain-language summary, or None on any failure (the
    report then falls back to its deterministic templated summary line)."""
    web = report.web_findings
    if not web:
        return None

    lines = [
        f"Provider: {report.provider_name or 'unknown'} | "
        f"Requested item: {report.item_name or 'unknown'} | "
        f"Category: {report.category_display_name}",
        f"Website-verifiable results: {report.summary_counts['found']} confirmed, "
        f"{report.summary_counts['not_found']} not confirmed, "
        f"{report.summary_counts['needs_review']} needs review. "
        f"{report.total_internal} items need human confirmation.",
        "",
        "Findings the tool computed:",
    ]
    for f in web:
        lines.append(f"- [{f.status}] {f.question} :: {f.note}")
    if report.research_note:
        lines.append(f"\nResearch note: {report.research_note}")

    user_prompt = (
        "Write the summary from these findings only:\n\n" + "\n".join(lines)
    )
    try:
        result = structured_completion(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            json_schema=_SCHEMA,
            schema_name="report_executive_summary",
        )
    except Exception:
        return None
    summary = (result.get("summary") or "").strip()
    return summary or None


__all__ = ["generate_executive_summary"]
