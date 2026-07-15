"""Orchestrates one full checklist run: fetch the provider page once, then
dispatch each criterion to its configured check_type. No category name is
ever referenced here — everything category-specific comes from the
ChecklistConfig (config/checklists/*.yaml) and the extracted field values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from preapproval_tool.checklist_engine.models import ChecklistConfig, Criterion
from preapproval_tool.evidence.capture_service import EvidenceCaptureService
from preapproval_tool.evidence.models import EvidenceItem
from preapproval_tool.evaluation.exclusion_list import evaluate_exclusion_list
from preapproval_tool.evaluation.fee_match import evaluate_fee_match
from preapproval_tool.evaluation.llm_judge import judge_criterion
from preapproval_tool.evaluation.models import Finding
from preapproval_tool.evaluation.rule import evaluate_rule
from preapproval_tool.evaluation.text_utils import is_quote_grounded, strip_markdown
from preapproval_tool.extraction.models import ExtractedApplication
from preapproval_tool.research.blocked_detection import detect_blocked_page
from preapproval_tool.research.error_messages import humanize_fetch_failure
from preapproval_tool.research.fetcher import fetch_page
from preapproval_tool.research.link_discovery import (
    find_candidate_subpages,
    page_identity as _page_identity,
    same_site_candidates,
    site_root,
)
from preapproval_tool.research.link_ranker import rank_links
from preapproval_tool.research.models import FetchResult, PageCapture
from preapproval_tool.security.url_guard import UnsafeURLError

# Criteria whose question/id concerns a fee, price, or schedule are the ones
# that actually benefit from a follow-up subpage fetch (a "Pricing" or
# "Classes" page the homepage alone doesn't carry) — kept generic/keyword-
# based rather than a per-category list so a new checklist config needs no
# changes here to get the same behavior.
_SUBPAGE_HELPFUL_KEYWORDS = ("fee", "price", "schedule")

# A judgment call the model itself flagged as low-confidence gets one
# independent second opinion before being shown to a reviewer — bounded cost
# (one extra LLM call only for the criteria that need it), catching the kind
# of run-to-run inconsistency ambiguous pages can produce.
_CONFIDENCE_RECHECK_STATUSES = ("found", "not_found")


@dataclass
class EvaluationRun:
    findings: list[Finding]
    fetch_result: FetchResult | None
    fetch_error: str | None  # set if the URL itself was unsafe/missing
    research_note: str | None = None  # e.g. "form link dead, used homepage instead"


def _normalize_snippet(value: str | None) -> str | None:
    """Some models occasionally emit the literal string "null" instead of a
    JSON null for an optional field even under strict schema mode. Treat that
    (and blank strings) the same as an absent snippet.
    """
    if value is None:
        return None
    stripped = value.strip()
    if not stripped or stripped.lower() == "null":
        return None
    return value


def _item_name(checklist: ChecklistConfig, extracted: ExtractedApplication) -> str:
    if checklist.item_name_field:
        value = extracted.value(checklist.item_name_field)
        if value:
            return str(value)
    return str(extracted.value("provider_name") or "the requested item")


def _is_subpage_helpful_criterion(criterion: Criterion) -> bool:
    haystack = f"{criterion.id} {criterion.question}".lower()
    return any(kw in haystack for kw in _SUBPAGE_HELPFUL_KEYWORDS)


def _dispatch(
    criterion: Criterion,
    *,
    checklist: ChecklistConfig,
    extracted: ExtractedApplication,
    page_text: str,
) -> dict[str, str | None]:
    if criterion.check_type == "llm_judgment":
        return judge_criterion(criterion, page_text=page_text, form_context=extracted.values)
    if criterion.check_type == "fee_match":
        fee_value = extracted.value(checklist.fee_field) if checklist.fee_field else None
        return evaluate_fee_match(
            criterion,
            form_fee=float(fee_value) if fee_value is not None else None,
            item_name=_item_name(checklist, extracted),
            page_text=page_text,
        )
    if criterion.check_type == "exclusion_list":
        return evaluate_exclusion_list(criterion, item_name=_item_name(checklist, extracted))
    raise ValueError(f"Unknown check_type for a web-verifiable criterion: {criterion.check_type}")


def _evaluate_web_criterion(
    criterion: Criterion,
    *,
    checklist: ChecklistConfig,
    extracted: ExtractedApplication,
    page_text_for_llm: str,
    evidence_sources: list[tuple[PageCapture, EvidenceItem | None]],
    capture_service: EvidenceCaptureService,
    form_answer: str | None,
) -> Finding:
    """Runs one web-verifiable criterion's check, including the confidence-
    gated self-consistency re-check and evidence capture. `evidence_sources`
    is the ordered list of (page capture, its whole-page evidence item) this
    criterion may draw evidence from — normally just the original page, but
    two entries during a subpage-retry pass (original + followed subpage), so
    a targeted crop is taken from whichever page actually contains the quote.
    """
    result = _dispatch(criterion, checklist=checklist, extracted=extracted, page_text=page_text_for_llm)

    status = result["status"]
    confidence = _normalize_snippet(result.get("confidence"))
    note = result["note"] or ""
    short_note = _normalize_snippet(result.get("short_note")) or ""
    quoted = _normalize_snippet(result.get("quoted_snippet"))

    # Confidence-gated re-check: the model itself flagged this as borderline.
    # Spend one more independent call rather than trust a single pass — if
    # the two disagree, that disagreement *is* the signal this needs a human,
    # not a coin-flip between two plausible answers.
    if (
        criterion.check_type == "llm_judgment"
        and confidence == "low"
        and status in _CONFIDENCE_RECHECK_STATUSES
    ):
        second = _dispatch(criterion, checklist=checklist, extracted=extracted, page_text=page_text_for_llm)
        second_status = second["status"]
        if second_status != status:
            note = (
                f"{note} [Held at Needs Review: a low-confidence judgment was "
                f"independently re-checked and produced a different answer "
                f"('{status}' vs. '{second_status}'), so this is flagged for "
                "human review rather than guessed either way.]"
            ).strip()
            status = "needs_review"
            quoted = None
            short_note = "Needs Review — an automatic double-check gave an inconsistent answer."
        else:
            note = f"{note} [Independently double-checked due to low confidence — result was consistent.]".strip()

    # Evidence-integrity check: a quote is only usable as grounding if it
    # actually appears in a page we actually captured — an LLM claiming a
    # quote that isn't really there must never stand as proof. Check each
    # candidate source in order so a subpage-sourced quote is matched to the
    # subpage, not incorrectly compared against the original homepage text.
    grounded_capture: PageCapture | None = None
    if quoted:
        for src_capture, _ in evidence_sources:
            if is_quote_grounded(quoted, src_capture.text_content):
                grounded_capture = src_capture
                break
        if grounded_capture is None:
            note = (
                f"{note} [The model's quoted snippet could not be verified "
                "against the captured page content, so it was discarded and "
                "this finding was held at Needs Review.]"
            ).strip()
            quoted = None
            if status == "found":
                status = "needs_review"

    # One evidence image per finding, not two: a real targeted crop when we
    # can produce one, otherwise the single shared whole-page capture for
    # context — never both (see log.md Key Learnings, Sample 10 QA pass).
    targeted = None
    if status in ("found", "needs_review") and quoted and grounded_capture:
        targeted = capture_service.capture_targeted(
            grounded_capture,
            criterion_id=criterion.id,
            label=criterion.evidence_label or f"Evidence: {criterion.id}",
            locate_text=strip_markdown(quoted),
        )
    evidence: list[EvidenceItem] = []
    if targeted:
        evidence.append(targeted)
    else:
        fallback_whole_page = next(
            (wpe for cap, wpe in evidence_sources if grounded_capture is None or cap is grounded_capture),
            None,
        ) or next((wpe for _, wpe in evidence_sources if wpe), None)
        if fallback_whole_page:
            evidence.append(fallback_whole_page)

    # A website-verified "Found" must be backed by a readable, targeted crop of
    # the exact proof — a whole-page screenshot alone is not enough for an audit
    # (PM QA on Sample 10: negative claims like "no college credit"/"not
    # clinical" were marked Found off a silent page with only a whole-page
    # capture). If no targeted crop could be produced (no grounded quote, or the
    # exact text couldn't be located on the page), the claim isn't Found — hold
    # it at Needs Review. Deterministic rule checks (exclusion_list) carry their
    # own configured provenance and don't need a screenshot, so they're exempt.
    if status == "found" and criterion.check_type in ("llm_judgment", "fee_match") and targeted is None:
        status = "needs_review"
        note = (
            f"{note} [Held at Needs Review: the supporting text was found but a "
            "readable, targeted screenshot of the exact proof could not be "
            "produced, so a reviewer should confirm this directly on the site.]"
        ).strip()
        short_note = "Needs Review — proof found in text but not capturable as a targeted screenshot."

    return Finding(
        criterion.id,
        criterion.question,
        status,  # type: ignore[arg-type]
        strip_markdown(note),
        short_note=strip_markdown(short_note),
        quoted_snippet=strip_markdown(quoted) if quoted else None,
        evidence=evidence,
        form_answer=form_answer,
        confidence=confidence,
    )


# Bounds on the pricing navigator's autonomy: it may open at most this many
# extra pages total, and follow links at most this many hops deep from the
# page we started on. This is the line between "a bounded, auditable helper"
# and "an unbounded agent loop" — deliberately small and fixed, never
# model-controlled (see docs/limitations-and-assumptions.md).
_NAV_MAX_FETCHES = 3
_NAV_MAX_DEPTH = 2


def _run_pricing_navigator(
    findings: list[Finding],
    *,
    checklist: ChecklistConfig,
    extracted: ExtractedApplication,
    start_capture: PageCapture,
    start_whole_page_evidence: EvidenceItem | None,
    capture_service: EvidenceCaptureService,
    progress: Callable[[str], None],
) -> None:
    """Bounded, best-effort navigator for the fee/price/schedule criteria that
    the first page couldn't answer. From the starting page it lets the LLM
    pick the most promising links (falling back to keyword ranking), follows
    them up to `_NAV_MAX_DEPTH` hops and `_NAV_MAX_FETCHES` pages total, and
    re-checks the still-unresolved criteria against each page it opens. A page
    that yields the exact price resolves the criterion; a page that only shows
    a representative/example price upgrades the finding with that grounded
    example (and its screenshot) while honestly staying Needs Review. Never
    raises — a smartness enhancement must never break the primary results.
    """
    web_criteria_by_id = {c.id: c for c in checklist.web_criteria}
    findings_by_id = {f.criterion_id: f for f in findings}
    needs_help_ids = {
        cid
        for cid, f in findings_by_id.items()
        if f.status == "needs_review"
        and cid in web_criteria_by_id
        and _is_subpage_helpful_criterion(web_criteria_by_id[cid])
    }
    if not needs_help_ids:
        return

    ranking_question = "; ".join(web_criteria_by_id[cid].question for cid in needs_help_ids)
    visited: set[str] = {_page_identity(start_capture.final_url)}
    # Grows as we visit pages, so a quote the model returns can be grounded
    # against whichever page it actually came from.
    evidence_sources: list[tuple[PageCapture, EvidenceItem | None]] = [
        (start_capture, start_whole_page_evidence)
    ]
    frontier: list[tuple[PageCapture, int]] = [(start_capture, 0)]
    fetches_left = _NAV_MAX_FETCHES

    while frontier and needs_help_ids and fetches_left > 0:
        current, depth = frontier.pop(0)
        if depth >= _NAV_MAX_DEPTH or not current.links:
            continue

        candidates = same_site_candidates(
            current.links, base_url=current.final_url, exclude_urls=list(visited)
        )
        if not candidates:
            continue
        ranked = rank_links(ranking_question, candidates, limit=2)
        if not ranked:
            keyword_ranked = find_candidate_subpages(
                current.links, base_url=current.final_url, exclude_url=current.final_url
            )
            ranked = [u for u in keyword_ranked if _page_identity(u) not in visited]
        if not ranked:
            continue

        for candidate_url in ranked:
            if not needs_help_ids or fetches_left <= 0:
                break
            identity = _page_identity(candidate_url)
            if identity in visited:
                continue
            visited.add(identity)
            fetches_left -= 1

            try:
                progress(f"Checking a linked page for missing details ({candidate_url})...")
                sub_result = fetch_page(candidate_url)
            except Exception:
                continue
            if not sub_result.accessible or not sub_result.capture:
                continue
            sub_cap = sub_result.capture
            try:
                sub_wpe = capture_service.capture_whole_page(
                    sub_cap, slug=f"{checklist.category_id}-subpage"
                )
            except Exception:
                sub_wpe = None
            evidence_sources.append((sub_cap, sub_wpe))

            # Keep the start page's context alongside the new page but stay
            # under llm_judge/fee_match's own 12000-char prompt cap so the
            # freshly-fetched page (the whole point) can't be truncated away.
            combined_text = (
                f"{start_capture.text_content[:4000]}\n\n"
                f"--- ADDITIONAL PAGE CHECKED: {sub_cap.final_url} ---\n"
                f"{sub_cap.text_content[:7500]}"
            )

            resolved_ids = []
            for cid in list(needs_help_ids):
                criterion = web_criteria_by_id[cid]
                try:
                    nf = _evaluate_web_criterion(
                        criterion,
                        checklist=checklist,
                        extracted=extracted,
                        page_text_for_llm=combined_text,
                        evidence_sources=evidence_sources,
                        capture_service=capture_service,
                        form_answer=findings_by_id[cid].form_answer,
                    )
                except Exception:
                    continue
                if nf.status != "needs_review":
                    nf.note = f"{nf.note} (Resolved after checking a linked page: {sub_cap.final_url})".strip()
                    findings_by_id[cid] = nf
                    resolved_ids.append(cid)
                elif nf.evidence and not findings_by_id[cid].evidence:
                    # Still can't confirm the exact price, but this page gave us
                    # a grounded example (with a screenshot) the original page
                    # lacked — a strictly more useful Needs Review for a human.
                    nf.note = f"{nf.note} (Found on a linked page: {sub_cap.final_url})".strip()
                    findings_by_id[cid] = nf

            for cid in resolved_ids:
                needs_help_ids.discard(cid)

            # Allow one deeper hop from this page if anything's still missing.
            frontier.append((sub_cap, depth + 1))

    for i, f in enumerate(findings):
        replacement = findings_by_id.get(f.criterion_id)
        if replacement is not None and replacement is not f:
            findings[i] = replacement


def run_evaluation(
    checklist: ChecklistConfig,
    extracted: ExtractedApplication,
    capture_service: EvidenceCaptureService,
    on_progress: Callable[[str], None] | None = None,
) -> EvaluationRun:
    def progress(message: str) -> None:
        if on_progress:
            on_progress(message)

    findings: list[Finding] = []
    url_value = extracted.value("webpage_url") or extracted.value("item_link")

    fetch_result: FetchResult | None = None
    fetch_error: str | None = None
    whole_page_evidence: EvidenceItem | None = None

    research_note: str | None = None

    progress("Validating the provider URL...")
    if not url_value:
        fetch_error = "No provider URL was found on the application form."
    else:
        try:
            fetch_result = fetch_page(str(url_value))
        except UnsafeURLError as exc:
            fetch_error = f"Provider URL failed safety validation: {exc}"

        # Recovery: the exact deep link on the form is dead (e.g. a stale
        # /join page that now 404s), but the provider's main site is usually
        # fine and reachable one level up. Back off to the homepage and work
        # from there rather than reporting the whole application unverifiable —
        # the navigator can then find the real membership/pricing page from
        # the homepage's links. Recorded transparently so the reviewer knows
        # we didn't check the exact page they listed.
        if fetch_result and not fetch_result.accessible and not fetch_error:
            root = site_root(str(url_value))
            if root and _page_identity(root) != _page_identity(str(url_value)):
                progress("The exact page on the form was unreachable — trying the provider's main site...")
                try:
                    root_result = fetch_page(root)
                except UnsafeURLError:
                    root_result = None
                if root_result and root_result.accessible:
                    fetch_result = root_result
                    research_note = (
                        f"The exact web address on the application form "
                        f"({url_value}) could not be opened, so this report was "
                        f"produced from the provider's main website ({root}) "
                        "instead. A reviewer should confirm the specific page "
                        "the form intended."
                    )

    blocked_reason: str | None = None
    if fetch_result and fetch_result.accessible:
        progress(f"Reading the public website ({fetch_result.capture.method})...")
        # The page loaded, but it may be an anti-bot / CAPTCHA wall rather than
        # the real content (Sample 07: Amazon's "continue shopping" bot check).
        # Detect that up front so we report it honestly and never let the LLM
        # describe a block screen as a normal page.
        blocked_reason = detect_blocked_page(
            fetch_result.capture.text_content, fetch_result.capture.page_title
        )
        progress("Capturing evidence...")
        whole_page_evidence = capture_service.capture_whole_page(
            fetch_result.capture, slug=checklist.category_id
        )
        if blocked_reason and not research_note:
            research_note = blocked_reason
    elif fetch_error:
        progress(f"Website could not be reached: {fetch_error}")
    else:
        progress("Website could not be reached after trying all fetch methods.")

    web_criteria = [c for c in checklist.criteria if c.verifiable == "web"]
    checked = 0
    for criterion in checklist.criteria:
        form_answer = extracted.checkbox_answers.get(criterion.id)

        if criterion.verifiable != "web":
            r = evaluate_rule(criterion)
            findings.append(
                Finding(
                    criterion.id,
                    criterion.question,
                    r["status"],  # type: ignore[arg-type]
                    r["note"],
                    group=criterion.group,
                    form_answer=form_answer,
                )
            )
            continue

        if fetch_error or not fetch_result or not fetch_result.accessible:
            # exclusion_list is a pure form-data check (item name vs. the
            # category's configured exclusion list) — it never needs the
            # fetched page, so a dead/unreachable provider link must not
            # block it. Everything else genuinely needs the page content.
            if criterion.check_type == "exclusion_list":
                result = evaluate_exclusion_list(
                    criterion, item_name=_item_name(checklist, extracted)
                )
                findings.append(
                    Finding(
                        criterion.id,
                        criterion.question,
                        result["status"],  # type: ignore[arg-type]
                        result["note"] or "",
                        form_answer=form_answer,
                    )
                )
                continue
            reason = fetch_error or humanize_fetch_failure(fetch_result, str(url_value) if url_value else None)
            findings.append(
                Finding(
                    criterion.id,
                    criterion.question,
                    "needs_review",
                    reason,
                    form_answer=form_answer,
                )
            )
            continue

        # Page loaded but it's a block/CAPTCHA wall: the exclusion-list check
        # (pure form data) can still run, but anything that reads page content
        # cannot be trusted — mark Needs Review with the honest blocked message
        # instead of asking the LLM to interpret an anti-bot shell.
        if blocked_reason and criterion.check_type != "exclusion_list":
            findings.append(
                Finding(
                    criterion.id,
                    criterion.question,
                    "needs_review",
                    blocked_reason,
                    form_answer=form_answer,
                    evidence=[whole_page_evidence] if whole_page_evidence else [],
                )
            )
            continue

        checked += 1
        progress(f"Checking application criteria ({checked} of {len(web_criteria)})...")
        findings.append(
            _evaluate_web_criterion(
                criterion,
                checklist=checklist,
                extracted=extracted,
                page_text_for_llm=fetch_result.capture.text_content,
                evidence_sources=[(fetch_result.capture, whole_page_evidence)],
                capture_service=capture_service,
                form_answer=form_answer,
            )
        )

    if fetch_result and fetch_result.accessible and fetch_result.capture and not blocked_reason:
        try:
            _run_pricing_navigator(
                findings,
                checklist=checklist,
                extracted=extracted,
                start_capture=fetch_result.capture,
                start_whole_page_evidence=whole_page_evidence,
                capture_service=capture_service,
                progress=progress,
            )
        except Exception:
            # The navigator is a bonus, never a requirement — a bug in it must
            # never cost the reviewer the (already-good) results from the
            # primary single-page pass.
            pass

    progress("Preparing the reviewer report...")
    return EvaluationRun(
        findings=findings,
        fetch_result=fetch_result,
        fetch_error=fetch_error,
        research_note=research_note,
    )
