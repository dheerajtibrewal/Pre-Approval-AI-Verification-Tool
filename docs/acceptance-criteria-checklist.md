# Acceptance Criteria Checklist

A literal, item-by-item walkthrough of `docs/Project-Brief.pdf` §8 (acceptance
criteria), §9 (deliverables), and §10 (constraints), against this repo's
actual state as of this writing — not a paraphrase. Each item names the
concrete file/behavior that satisfies it and, where relevant, an honest note
on how completely it's met.

## §8 — Acceptance criteria for a successful basic version

1. **Accepts a completed pre-approval application (one of the 7 forms).**
   `web/app.py::create_application` (upload) and `scripts/run_sample.py`
   (batch). All 7 categories are implemented and all 10 sample forms have
   been run — see `output/samples/`.
2. **Extracts the main request details (§4).**
   `extraction/field_extractor.py` — schema-validated LLM extraction driven
   entirely by each category's `config/checklists/*.yaml` `fields` list; no
   per-category code. Verified against all 10 samples' real header fields.
3. **Identifies the website/link to review.**
   `evaluator.py`'s `url_value = extracted.value("webpage_url") or
   extracted.value("item_link")` — generic across categories.
4. **Identifies the applicable category.**
   `categorization/classifier.py::classify` — deterministic
   template-signature match first, LLM fallback second, `CategoryAmbiguousError`
   if genuinely unclear. Verified: all 10 samples classify correctly with
   high confidence via the deterministic path (no LLM fallback needed).
5. **Applies the correct checklist and separates website-verifiable from
   internal items (§5).**
   Every `config/checklists/*.yaml` tags each criterion
   `verifiable: web | internal | document`; `ChecklistConfig.web_criteria` /
   `.internal_criteria` split on it. The report UI puts these in separate
   tabs (Findings vs. Internal Checks) so a reviewer can never mistake one
   for the other.
6. **Visits the website and gathers public evidence for website-verifiable
   items.**
   `research/fetcher.py` (Firecrawl primary, Playwright fallback) +
   `evidence/capture_service.py`.
7. **Captures date-stamped evidence** — whole-page capture, plus a labeled
   per-requirement screenshot for each confirmed item, each stamped with
   capture date/time and URL.
   `EvidenceCaptureService.capture_whole_page` / `.capture_targeted` burn a
   visible `Captured <UTC timestamp> · <URL>` watermark into every image
   (`capture_service.py::_watermark`) and record the same data as structured
   `EvidenceItem` fields (`captured_at`, `url`, `evidence_id`, `method`).
   A "targeted" label is only used when a real, distinct crop was actually
   obtained — otherwise honestly relabeled (see `docs/ux-and-evidence-integrity.md`).
8. **Marks items Not Found / Needs Review when evidence is absent or
   unclear.**
   Design principle enforced structurally, not just by prompt: a "Found"
   status without a real evidence capture is automatically downgraded to
   Needs Review in `Finding.__post_init__`. Demonstrated live, not just in
   theory — Sample 04 (Planet Fitness) and Sample 05 (Brooklyn Museum) both
   came back honestly Needs Review rather than guessed (see `log.md` Phase 3
   results table).
9. **Generates a readable report and summarizes results for the reviewer.**
   `report/generator.py` + `web/templates/report.html` — 5-tab workspace
   (Overview/Findings/Evidence/Internal Checks/Review & Export); see
   `docs/ux-and-evidence-integrity.md` for the design rationale.
10. **Lets the reviewer request basic changes to the report.**
    Override status + note, mark-reviewed, restore-original, and regenerate
    (re-run research from scratch while preserving reviewer decisions) — all
    on `web/app.py`'s `/applications/{id}/findings/{criterion_id}/*` and
    `/regenerate` routes, persisted in `ApplicationRecord.review_state` so
    they survive both a page refresh and a full regenerate.

**Note on §7's "ask for clarification" requirement**, which §8 doesn't
restate but is closely related: this build implements it as a **confirm-
before-research step** (`web/templates/confirm.html`) rather than a literal
back-and-forth chat question — the reviewer sees the extracted fields
(including a missing/wrong URL or an ambiguous category, both flagged) and
corrects them before research begins, instead of the tool asking a
free-form question first. This satisfies the same underlying goal (don't
silently proceed on bad input) but is worth being explicit that it's a
confirm/correct UI, not a conversational clarification exchange.

## §9 — Deliverables

1. **Finished product, runs on ≥3 samples, produces the report package for
   each.** Exceeded — all 10 samples run; **four committed as complete,
   validated audit packages** (report.pdf + report.html + report.json +
   evidence-manifest.json + run-metadata.json + evidence/), the rest as
   report.html + evidence/:
   - `output/samples/sample-01-gallopnyc/` — Community Class (4 Confirmed / 4 Needs Review / 12 internal)
   - `output/samples/sample-04-planet-fitness/` — Membership (0 / 3 / 5; location-specific pricing held Needs Review)
   - `output/samples/sample-08-weighted-blanket/` — OTPS (1 / 1 / 8; exclusion-list check + honest blocked-page handling)
   - `output/samples/sample-09-laguardia-ace/` — Transition Program (0 / 4 / 6)

   `validate_export` reports zero issues on all four (every Confirmed is backed
   by an on-disk capture; all HTML evidence references resolve for offline
   viewing). See README "Final sample runs" for the write-up.
2. **Git repository**, organized for a team to inherit: README, clear
   structure, config-driven checklists, tests where appropriate, no real
   participant data. All present — see the repo-hygiene checks below.
   *(Still the user's own action, not run by the agent: making the repo
   public, and the actual `git push`.)*
3. **A short video** — explicitly out of scope for this repo per the
   README's own precedence note (recorded on the F5 submission page
   instead, not a repo deliverable).

Also required by §9's closing paragraph, all present:
- Simple run instructions for a non-technical reviewer — README "Quickstart"
  and "Reviewer journey" sections.
- At least one sample output report with evidence captures — all 10 are
  committed.
- A note on how to add/change a form/checklist — README "Adding a new
  form/checklist," including the non-technical `/manage-checklists` UI path.
- A statement of limitations, assumptions, and production-readiness —
  `docs/limitations-and-assumptions.md`.

## §10 — Constraints, non-goals & data handling

- **Human-in-the-loop, always; never approves/denies.** Verified by a
  repo-wide grep for approval/denial language emitted by the tool itself
  (as opposed to the form's own printed "For office use only" fields) —
  none found. Every report footer states: *"This report assists a human
  reviewer and does not itself approve or deny this request."*
- **PHI / synthetic data only.** All 10 samples use fictional participants
  (first name + last initial, e.g. "Aaron M."). A repo-wide scan for SSN/
  phone-number/email patterns in `output/samples/` found none beyond the
  synthetic agency example addresses already in the provided sample PDFs.
- **No guessing on the checklist.** Structural, not just prompted: an
  LLM-claimed quote that can't be verified against the actually-captured
  page text is discarded and the finding held at Needs Review
  (`evaluation/text_utils.py::is_quote_grounded`, wired into
  `evaluator.py`). Exclusion-list gating is fully deterministic
  (`evaluation/exclusion_list.py`), never an LLM judgment call.
- **Out of scope, confirmed absent:** no Enterprise Manager/eVero
  integration, no participant-budget or Life Plan system integration, no
  payment/invoicing handling. Confirmed nowhere in `src/`.

## Repo hygiene (self-check before submission)

- [x] No API keys/secrets anywhere in the working tree (`.env` is
  git-ignored; `.env.example` has placeholder values only).
- [x] No real participant data — all sample data is fictional per the
  brief's own provided samples.
- [x] `config/checklists/` is genuinely config-driven — a repo-wide grep for
  hardcoded category-id strings in `src/` returns zero matches.
- [ ] `AI-CONVERSATION.md` — the required tools/models list is prepared, but
  the actual exported conversation transcript must be pasted in by the user
  (see the file itself and the README) — this is the one remaining manual
  step before submission, since only the user can export their own real
  session.
- [ ] Repo made public, pushed, and submitted at the F5 link — user's own
  action, not performed by the agent.
