# Project Log — Pre-Approval Website-Verification Tool

**This file is the project's brain.** Read it in full before starting any work
session on this repo. Update it — Current State, Remaining Work, and Key
Learnings — before ending any work session or handing off. This is a standing
rule from 2026-07-15 onward, not a one-time note.

---

## 1. What this project is

F5 Global Talent AI Specialist Pool take-home: build an AI-assisted tool that
reads a completed OPWDD Self-Direction pre-approval application (PDF),
researches the provider's public website, captures auditable evidence, and
produces a review-ready report with per-criterion Found/Not Found/Needs
Review/Internal findings. A human reviewer always makes the final
approve/deny call. Full requirements: `docs/Project-Brief.pdf` (authoritative
spec) and `docs/Short-Brief.pdf` (summary). `README.md` is authoritative over
both where they conflict. Full Phase 1 planning doc (requirements
traceability, architecture options, data/evidence models, threat model, etc.)
is not in this repo — it was produced in the planning conversation; this log
picks up from the approved decisions.

**Decided stack (approved in Phase 1):**
- Python backend (FastAPI + Jinja2 templates, no separate JS frontend
  framework)
- OpenAI (GPT models) for extraction, categorization fallback, grounded
  criterion judgment
- Firecrawl as primary website fetch/render layer, local Playwright as
  fallback + targeted-crop capture
- Web UI (not CLI), Apple-inspired restraint/hierarchy/whitespace — original
  components, system fonts, not a literal Apple UI clone
- All 10 sample applications will eventually be run and committed (not just
  the brief's minimum of 3)

---

## 2. Architecture (current)

```
config/
  checklist_schema.json          JSON Schema every checklist YAML must satisfy
  checklists/                    all 7 categories implemented (config-driven)
    community-classes.yaml
    coaching.yaml
    memberships.yaml
    hri.yaml
    otps.yaml
    transition-program.yaml
    appeals.yaml                 reuses community-classes' web criteria verbatim
                                 at load time (loader.py::_apply_appeal_reuse)

src/preapproval_tool/
  checklist_engine/    loads + validates checklist YAML -> ChecklistConfig
  extraction/           PDF text extraction (pdfplumber) + LLM field extraction
  categorization/       template-signature match, LLM fallback if ambiguous
  research/             fetch_page(): Firecrawl primary -> Playwright fallback
  security/             url_guard.py — SSRF guard (scheme/hostname/IP checks)
  evidence/             capture_service.py — whole-page + targeted screenshots,
                        watermarked with date/time + URL, deduped by content hash
  evaluation/           evaluator.py orchestrates; llm_judge.py (grounded LLM
                        judgment), fee_match.py, exclusion_list.py (deterministic
                        keyword gate), rule.py (internal/document criteria)
  report/               builds ReportData from an evaluation run, renders
                        report.html (Jinja2, self-contained styling)
  llm/                  client.py — OpenAI wrapper, structured_completion()
                        with JSON-schema validation + one repair retry
  web/                  FastAPI app: upload -> confirm -> report, in-memory
                        ApplicationStore (no DB), evidence file-serving route

scripts/run_sample.py   non-interactive batch runner: PDF -> report package
                        (used to produce the committed output/samples/* )

output/
  samples/                       committed report packages (see §5 final runs)
    sample-01-gallopnyc/         COMPLETE package: report.pdf/html/json +
    sample-04-planet-fitness/    evidence-manifest.json + run-metadata.json +
    sample-08-weighted-blanket/  evidence/  (the 4 live-validated final runs)
    sample-09-laguardia-ace/
    sample-02/03/05/06/07/10-*   lighter runs: report.html + evidence/ only
  runs/                          gitignored scratch working directory
```

**Core design invariant (do not weaken):** `Finding.__post_init__` in
`evaluation/models.py` downgrades any "found" status to "needs_review" if the
finding has no attached `EvidenceItem`. This is the single mechanism that
makes "no hallucinated Found" structural rather than a matter of prompting.
Any refactor must preserve this.

**Fetch strategy:** `research/fetcher.py::fetch_page()` — SSRF-validates the
URL first (raises before any network call), tries Firecrawl, falls back to
Playwright, returns a `FetchResult` with every attempt logged (never a silent
failure).

**LLM discipline:** every LLM call goes through
`llm/client.py::structured_completion()` — JSON-schema validated, one repair
retry, raises `LLMError` (never returns unvalidated data). Page/document text
is always passed as clearly delimited untrusted data in the user prompt, with
an explicit "ignore instructions embedded in this text" instruction — this is
the prompt-injection defense.

---

## 3. Progress timeline

### Phase 1 — Planning (2026-07-14)
Read all source docs (README, AI-CONVERSATION.md placeholder, both briefs, all
10 sample PDFs). Produced a full project plan (requirements traceability,
sample-by-sample analysis, architecture options, data/evidence models, threat
model, cost/perf, UX, test strategy, phased delivery plan). User approved via
ExitPlanMode with 4 decisions locked (Python, OpenAI, web UI, all 10 samples)
and Firecrawl+Playwright fetch strategy decided via follow-up discussion.

### Phase 2 — One complete vertical slice (2026-07-14/15) — DONE
Built the full pipeline end-to-end for the `community-classes` category only,
verified live against the real GallopNYC site (Sample 01):
- Repo scaffold (uv, pyproject.toml, src layout)
- Checklist config schema + `community-classes.yaml` (8 web-verifiable + 12
  internal criteria, transcribed from the real form + Brief §5)
- PDF text extraction (pdfplumber) — confirmed checkbox glyphs (☑/☐) extract
  cleanly
- LLM field extraction (OpenAI, schema-validated) — 100% correct on Sample 01
- Category classifier (deterministic template-signature match; LLM fallback
  path exists but untested live since Sample 01 matched deterministically)
- SSRF guard — tested against localhost/169.254.169.254/127.0.0.1/10.0.0.0/8/
  file:// , all correctly blocked; real public URL correctly allowed
- Firecrawl + Playwright two-tier fetch — both paths verified live
- Evidence capture + watermarking (date/time + URL burned into image),
  content-hash dedup
- Deterministic exclusion-list gate — unit-verified against Sample 07's
  laptop (correctly flags "Computer Hardware" overlap) and Sample 06's grab
  bar (correctly passes)
- Report generator + Jinja2 template (single long page, light/dark, lightbox)
- FastAPI web app: upload -> confirm/edit extraction -> research -> report,
  plus reviewer override controls and a "regenerate" button
- `scripts/run_sample.py` batch runner
- **First committed sample: `output/samples/sample-01-gallopnyc/`** — real
  live run, 4 Found / 0 Not Found / 4 Needs Review / 12 Internal, honest
  nuanced findings (did not blindly mark "open to public" or "non-clinical"
  Found despite GallopNYC's dual therapeutic/recreational framing)

### Phase 2.A — UX/reviewer-experience hardening (2026-07-15) — DONE
Triggered by PM feedback after testing Sample 01 in-browser. Scope: **not** a
backend rebuild — restructure the reviewer experience (information
architecture, evidence viewer, progressive disclosure, accessibility,
responsiveness), fix concrete polish bugs, add security/QA test coverage, and
document. Full instructions and acceptance criteria are the PM feedback
message dated 2026-07-15 — treat that message as the spec of record for this
phase. Explicitly NOT in scope for 2.A: additional sample categories/runs
(that's Phase 3).

**What shipped:**
- Tabbed reviewer workspace (Overview / Findings / Evidence / Internal
  Checks / Review & Export) replacing the single long-scroll report —
  ARIA tablist, hash-synced, keyboard arrow-key navigation.
- Non-technical Overview with plain-language summary, fee comparison,
  attention items, and a "how to read this report" legend.
- Findings tab: progressive disclosure (`<details>` per finding), status
  filters, live search, and an "application answer vs. website
  verification" comparison — powered by a new deterministic checkbox-answer
  parser (`extraction/checkbox_parser.py`) that reads the applicant's own
  YES/NO answers straight off the PDF.
- Evidence-integrity hardening: quote-grounding validation
  (`is_quote_grounded`) downgrades any LLM quote that can't be verified
  against the actual captured page text; targeted evidence is only ever
  labeled "targeted" when a real crop was obtained, otherwise honestly
  labeled full-page; markdown artifacts (`**bold**`) stripped from all
  displayed quotes/notes.
- Evidence viewer overhaul: zoom (fit-width/full-res), download, source
  URL/title/timestamp/evidence ID always shown, native `<dialog>` for focus
  trap + Escape-to-close.
- Reviewer-override persistence bug fixed: overrides used to be silently
  lost on "Regenerate report" (fresh evaluation rebuilt Finding objects from
  scratch). Now `ApplicationRecord.review_state` persists independently and
  is reapplied after every fresh evaluation — verified by the E2E test.
  Added mark-reviewed and restore-system-result actions, full history/audit
  trail per finding, and a review-progress indicator ("N of M reviewed").
- Real backend-driven research progress screen: background thread +
  polling `/status` endpoint reporting actual pipeline stage, replacing the
  synchronous blocking wait.
- Extraction confirmation page: category override selector, PII/request-info
  section separation, URL format validation, "why confirm this" explainer.
- Review & Export tab: completion checklist, and three real downloads
  (report.html, report.json, complete package.zip with evidence + reviewer
  overrides), all backed by `web/export.py::validate_export` running a
  runtime integrity re-check independent of construction-time guarantees.
- Internal Checks: criterion-specific `explanation` + `group` fields added
  to the checklist schema/config, replacing one generic boilerplate line
  with per-criterion, grouped explanations.
- Polish: favicon 404 fixed (inline SVG route), no application-generated
  console errors (verified via real Playwright console/pageerror listeners),
  no horizontal overflow at 390/768/1280px (verified).
- Full pytest suite added: unit (exclusion-list, checkbox parser, text
  utils, Finding invariant), schema validation, security (SSRF, upload
  validation, export validation), and a gated live E2E acceptance test
  covering the full 15-step Sample 01 flow — all passing (42 non-e2e + 1
  e2e). See §7 for exact commands.
- Documentation: README rewritten (quickstart, architecture, reviewer
  journey, evidence model, security, accessibility, limitations, test
  commands), `docs/limitations-and-assumptions.md` and
  `docs/ux-and-evidence-integrity.md` added.
- Sample 01's committed package (`output/samples/sample-01-gallopnyc/`)
  regenerated against the new UI so the committed deliverable matches what
  ships.

Two real bugs were found and fixed *during this phase's own testing* (not
pre-existing from Phase 2) — see §6 Key Learnings: a `|tojson`-inside-
`onclick` HTML-escaping bug that silently broke the evidence lightbox, and
the override-persistence-on-regenerate bug above.

### Phase 3 — Full category + sample coverage (2026-07-15) — DONE
Authored the 6 remaining checklist configs (Coaching, Memberships, HRI,
OTPS, Transition Program, Appeals) directly from the real sample PDFs' text
(not guessed), and ran all 9 remaining samples live end-to-end. See §5 for
the full per-sample results table and the two engine fixes this phase
required (exclusion-list/fetch-dependency bug; fee_match cap-ceiling mode).
All 7 categories and all 10 samples are now implemented and verified —
nothing left in the brief's required scope. See §5 for details.

---

## 4. Known bugs already fixed (do not reintroduce)

1. **Starlette `TemplateResponse` signature** — this project's installed
   Starlette version requires `templates.TemplateResponse(request, name,
   context)` with `request` as a positional arg, NOT
   `TemplateResponse(name, {"request": request, ...})` (the old/common
   pattern). Using the old pattern raises `TypeError: unhashable type: dict`.
2. **`.env` loading order** — `load_dotenv()` must run at package import time
   (`src/preapproval_tool/__init__.py`), not just in one submodule
   (`llm/client.py`). Any module that reads an env var directly (e.g.
   `research/firecrawl_client.py`) will see it unset if dotenv hasn't loaded
   yet when that module is imported first/standalone.
3. **Literal `"null"` string from LLM** — despite strict JSON-schema mode and
   explicit prompt instructions, the model sometimes emits the JSON string
   `"null"` instead of an actual `null` for an optional field
   (`quoted_snippet`). Fixed via `_normalize_snippet()` in
   `evaluation/evaluator.py` — treat a blank string or the literal text
   "null" (case-insensitive) as absent. Apply this pattern to any other
   optional string field an LLM populates.
4. **Playwright screenshot lazy-load timing in automated tests** — screenshotting
   a page immediately after `goto()` can catch `loading="lazy"` images before
   they've rendered, producing a false "broken image" look. Always
   `wait_for_load_state("networkidle")` (+ a short explicit wait if needed)
   before screenshotting for QA.
5. **Playwright `.click()` default timeout on slow server actions** — clicking
   a button whose POST handler does multi-second work (LLM calls, page
   fetches) can hit Playwright's default 30s action timeout even before your
   own `wait_for_load_state` call runs. Pass an explicit longer `timeout=` to
   `.click()` when the click triggers a slow server round-trip.
6. **Locating text for a targeted evidence crop via a short/generic keyword is
   unsafe** — `page.get_by_text("per", exact=False)` matched a false element
   because "per" is a substring of "experience". Always locate using an
   *exact quoted snippet* returned by the grounded LLM call, never a
   hand-picked short keyword.

---

## 5. Remaining work

**Current state (2026-07-15, final submission pass):** Feature-complete. All 7
categories implemented (config-driven), all 10 samples run live. Four samples
(01 GallopNYC, 04 Planet Fitness, 08 Weighted Blanket, 09 LaGuardia ACE) are
committed as **complete validated packages** under `output/samples/` — each with
report.pdf, report.html, report.json, evidence-manifest.json, run-metadata.json,
and evidence/. `validate_export` reports zero issues on all four (every Confirmed
is backed by an on-disk capture). The other six categories have lighter committed
runs (report.html + evidence/). Full test suite green; secret scan clean; nothing
committed to git yet (awaiting user approval of the final diff).

**Remaining work:** none blocking submission. Optional/future: regenerate the six
lighter runs as full packages via the now-unified `scripts/run_sample.py` (it now
emits the complete package via `export.write_full_package`); production-readiness
items tracked in `docs/limitations-and-assumptions.md` (datastore, task queue,
PHI redaction, RBAC, audit DB).

### Phase 5.12 — Final documentation & submission pass (2026-07-15)

Directive: package the four user-tested samples as complete audit bundles, wire
them into README, add a runtime-cost section, de-stale log.md, add the AI
transcripts, and verify the whole repo opens/runs end-to-end. No product-logic or
UI changes. Not committed (awaiting final-diff approval).

- **Unified export path.** Refactored `web/export.py` builders (`build_report_json`,
  `build_evidence_manifest`, `build_run_metadata`, `validate_export`) to take a
  `ReportData` instead of an in-memory `ApplicationRecord`, and added
  `write_full_package(report, out_dir)`. `scripts/run_sample.py` now emits the
  full committable package (report.pdf/json + both manifests), so an offline
  committed sample and a reviewer's in-app download zip can never drift. Updated
  the two record-based call sites (app.py, export-validation tests).
- **Four final packages assembled** from the user's live-tested runs: real
  report.html/pdf/evidence copied verbatim from `output/runs/<hash>/`, report.json
  from the user's TestCases, and the two manifests generated by the shared
  builders off a faithfully reconstructed ReportData. No re-render, no paid
  re-run — the tested output is preserved exactly. Verified: all JSON valid, all
  HTML evidence refs resolve (open with no server), validation_issues empty.
  Renamed to spec folder names; removed the two superseded partial folders
  (sample-08-otps-weighted-blanket, sample-09-laguardia-cc).
- **README:** added "Final sample runs" table (scenario / result / one honest
  Needs-Review outcome / links per sample), added "Runtime cost and usage" (hard
  bounds from code + observed counts + clearly-labelled runtime estimate; no
  invented dollar figures), updated Status to link the four.
- **AI transcripts:** committed the text-only Claude Code build transcript
  (`docs/ai-transcripts/claude-code-build-transcript.md`, images/asset blobs
  stripped, tool calls reduced to one-line markers) alongside the GPT thread;
  AI-CONVERSATION.md §2 now points to both.
- **log.md:** architecture tree now lists all 7 checklist configs; removed the
  "ONLY category implemented" line; Current State / Remaining Work refreshed.

### Phase 5.11 — Senior QA sweep from shared sample outputs (2026-07-15)

User shared live PDFs/screenshots for Samples 04 (Planet Fitness), 08 (weighted
blanket), 09 (LaGuardia ACE) and flagged a "serious bug" on Sample 09: the header
read `X — X` (duplicated) and the evidence was blank. Three real defects found and
fixed deterministically (all offline; full suite 136 → **143 passing**):

**1. Duplicated report headline (`report/models.py`, `report.html`).** Forms that
list the provider AS the requested item (LaGuardia's transition program) rendered
`item — provider` as "LaGuardia… — LaGuardia…". Added `ReportData.display_title`:
collapses to one name when item == provider (case-insensitive), degrades gracefully
if either is missing. Both title lines (PDF cover + web header) now use it.
Test: `tests/unit/test_report_display_title.py`.

**2. False-positive "blocked" verdict on legitimate pages
(`research/blocked_detection.py`) — this was the real cause of Sample 09's "no
evidence".** LaGuardia is a `.edu` that loads fine for a human, but the report said
"the provider blocked automated access (an anti-bot or CAPTCHA check…)". Root cause:
the signature list contained a **bare `"captcha"` substring**. Legitimate .edu/
marketing pages routinely embed Google **reCAPTCHA** on a search/newsletter form,
so the rendered text contains "captcha" without the page being blocked at all — the
match suppressed all real research and left a near-blank capture. Removed the bare
substring; real challenge screens are still caught by the specific phrases ("enter
the characters you see below", "robot check", "verify you are a human", …) and the
tiny-shell heuristic. Amazon's wall (Sample 08) still trips correctly. Regression
test added (a working page embedding reCAPTCHA must NOT be flagged).

**3. Corrupted legend text at PDF page breaks (`report.html`).** In blocked-style
reports (Samples 04, 09) the "How to read this report" legend's last row spilled
onto its own page and rendered with jammed letter-spacing ("H umanConfirmation",
"Thiscan'tbechecked…") — a Chromium print bug when a text line is cut mid-height by
a page boundary. The legend card is intentionally breakable (fills whitespace), but
each `.legend-item`/`summary` is now `break-inside: avoid`, so a break only ever
lands *between* rows. Verified by rendering a real 4-page PDF and confirming the
legend text extracts intact and the title is not duplicated.

Boundary honesty: I fixed the structural defects visible in the shared outputs; a
full 10-sample re-verification still needs the user's live paid runs. Sample 09
specifically should be re-run — with the block false-positive gone it will now
research the page and produce real evidence + findings instead of all-Needs-Review.

### Phase 5.10 — Final accuracy & export QA (PM punch-list, 2026-07-15)

PM (GPT-5.6) produced an 8-point "Phase 5.9 — Final Accuracy and Export QA"
list from live QA of Samples 02/04/07/10. Triaged each honestly first (agreed
with 1,3,4,5,6,8 as real blockers; did 2 as a structural fix + test rather than
a live-verdict guarantee; declined the OCR half of 7 as out-of-scope, did the
safe-degradation half). All mocked/offline; live re-runs of the four samples
left to the user. Full suite 111 → **136 passing**.

**1. Location/tier-specific pricing never confirmed (`fee_match.py`).** Sample
04 confirmed a Newark, NJ club's $15 as the applicant's fee — a branch price
the form never named. Added a `price_scope` field to the extractor
(universal | location_specific | tier_specific | unknown); when a found price
is location/tier-specific it's rerouted to `_branch_price_example()` →
Needs Review with an "Example price — not confirmed for this application" note,
regardless of cap vs. exact-match mode. `price_scope: universal|unknown` still
confirms normally.

**3 + 4. Absence isn't proof + website-Found requires a targeted crop
(`llm_judge.py`, `evaluator.py`).** Sample 10 marked "college credits (must be
NO)" and "clinical (must be NO)" as Found off a *silent* page. Two-layer fix:
(a) prompt hardening — "'The page does not mention X' is always needs_review,
never found"; (b) deterministic backstop — a Found from `llm_judgment`/
`fee_match` now REQUIRES a readable targeted crop; if none can be produced (no
grounded quote, or the text can't be located), it's held at Needs Review.
`exclusion_list` (deterministic provenance) is exempt. The absence-Found cases
have no real quote → no crop → auto-downgraded.

**5. Blocked/CAPTCHA detection (`research/blocked_detection.py`, `evaluator.py`).**
Sample 07's Amazon bot wall ("Click the button below to continue shopping") was
described as a normal page. New conservative detector (known signatures + a
tiny-shell heuristic); when blocked, web criteria are held at Needs Review with
"The provider blocked automated access…", the LLM is skipped entirely, the
navigator is skipped, the block screen is still captured as honest evidence, and
a research_note surfaces it. exclusion_list still runs.

**6. Export integrity (`web/export.py`, `report.html`, test).** Static
`report.html` rendered the server-only Download card with `app_id=None` →
`/applications/None/export/...` broken links; now all server-route controls are
gated on `interactive` (verified: 0 `/applications/` refs in static HTML, 7 in
interactive). Zip gained `evidence-manifest.json` + `run-metadata.json`
alongside report.pdf/html/json + reviewer_overrides. New
`test_export_package.py` unzips and asserts every required member + that every
referenced evidence file exists.

**8. PDF pagination (`report.html`).** Sample 10's appeal cover spilled a
near-blank page; Sample 07 had a blank trailing page + a garbled/overlapping
footer. Fixes: product bar hidden in pdf_mode (no stray element between cover
and content), compact cover reliably fits one page incl. the longer appeal
cover, footer made `break-inside: avoid`. New regression test
`test_no_near_empty_pages_in_the_appeal_pdf` renders the appeal PDF and asserts
no interior page is near-empty.

**2. Appeal consistency (`checklist_engine/loader.py`, regression test).** The
regression test caught a REAL drift: appeals.yaml's `published_fees` had lost
its `form_question`, so the checkbox parser matched differently than the base
Community-Class config (a genuine source of the 02-vs-10 divergence). Rather
than hand-patch one field, the loader now REPLACES an appeal's web criteria
with the base category's web criteria verbatim (`_apply_appeal_reuse`), keeping
the appeal's own internal + appeal-review criteria — drift is now structurally
impossible. Verdict-level cross-run consistency is further helped by fixes 3/4.

**7 (lite). Low-text/scanned safe degradation (`field_extractor.py`, test).**
Declined a full OCR/rotation pipeline (out of scope). Did the honest part: when
a PDF has no usable text layer, every field is flagged low-confidence for
reviewer confirmation (not trusted as a clean read) with a clear "may be a
scanned image or rotated page" warning — never fabricated.

### Phase 5.9 — Documentation pass: checklist publish/rollback + three-model disclosure (2026-07-15)

Docs-only follow-up (no code changed):

- **README `Adding a new form/checklist`** expanded with the full
  draft → review-page → validate → (optional) test → **Publish** workflow, and
  a new **"Undoing an edit"** paragraph: before publish, discarding the draft
  keeps the live list untouched; after publish there is **no in-app rollback**
  (publish `write_text`-overwrites the YAML with no backup — verified in
  `web/app.py::publish_draft` + `draft_store.py`), so recovery is via
  `git restore config/checklists/<id>.yaml` or re-entering the old values.
- **Corrected a factual error** introduced earlier this session: checklist
  drafts are **disk-backed** (`data/checklist_drafts/*.json`, survive restart),
  not in-memory — it's `ApplicationRecord` *review* state that's in-memory. Both
  README and this understanding now match `draft_store.py`.
- **Roadmap item #5** upgraded to "review-gated, **versioned** publishing" —
  approval step + retained prior version for one-click rollback + audit-logged.
- **AI-CONVERSATION.md §1 (Tools & Models)** rewritten to disclose the real
  three-model *build* strategy, split from the in-product model: **GPT-5.6
  ("Soul")** as the planning / product-management / QA-strategy layer (project
  scaffold, phase planning/review, PM-style suggestions); **Claude Code +
  Sonnet 5** for building the base infrastructure (throughput); **Claude Code +
  Opus 4.8** for the final comprehensive QA/analysis/hardening phase (depth of
  reasoning to catch loose ends). In-product runtime model remains **GPT-4o**
  only, now documented with all five bounded uses (extraction, category
  fallback, grounded judgment, navigator link-ranking, grounded summary).

### Phase 5.8 — Pricing intelligence, humanized messages, smarter report (2026-07-15)

User QA on Samples 4 (Planet Fitness) and 5 (Brooklyn Museum) surfaced three
structural gaps, all confirmed by re-reading the code path end-to-end before
building. User was asked (AskUserQuestion) to choose the direction on the two
choices that touch cost and the no-fabrication rule; answers drove the design.

**1. Deeper, smarter pricing navigation.** The old `_try_subpage_rescue`
followed keyword-ranked links exactly one hop and only ran when the form URL
fetched successfully. That couldn't reach PF's price (two hops deep:
homepage → club finder → a club's `/offers`), missed good links keyword
ranking drops (Brooklyn's "Become a Member" — `/become-a-member` scores 0
against the keyword list), and never ran at all when the form URL 404'd
(Brooklyn's `/join`). Replaced with `_run_pricing_navigator`
(`evaluation/evaluator.py`): a bounded BFS that lets the LLM pick the most
promising same-site links (`research/link_ranker.py`, fallback to keyword
ranking), follows up to `_NAV_MAX_DEPTH=2` hops / `_NAV_MAX_FETCHES=3` pages,
and re-checks the still-unresolved fee/price/schedule criteria against each
page. Bounds are fixed constants, never model-controlled — a bounded auditable
helper, not an agent loop. Added `same_site_candidates()` (unfiltered,
LLM-rankable) and `site_root()` to `research/link_discovery.py`;
`_page_identity` made public as `page_identity`.

**2. Dead-URL recovery.** In `run_evaluation`, when the form's exact URL is
unreachable but the site root isn't, the tool now backs off to the homepage,
researches from there, and records a transparent `research_note`
("...produced from the provider's main website instead...") threaded through
`EvaluationRun → build_report_data → ReportData.research_note` and shown as a
"How this was researched" info-box. Never silently substitutes pages.

**3. Honest location/tier pricing.** Per the user's explicit choice
("Needs Review + clear explanation", and "tell the user what's missing in
their form"), `fee_match.py` gained `missing_input` / `example_amount` /
`example_quote` schema fields and `_no_price_diagnostic()`: when no single
price can be pinned, it names what the form left unspecified (e.g. "a specific
club location") and surfaces a clearly-labelled *example* price — passed
through as the quoted_snippet so it gets grounded and screenshotted like any
other evidence — while the status stays Needs Review. Never presents an
example as the confirmed price.

**4. Humanized reviewer messages.** `research/error_messages.py`
(`humanize_fetch_failure`) turns "Firecrawl reported HTTP 404 for https://..."
into plain language ("The exact web address... doesn't exist anymore — the
page returned 'not found'...") with the raw string kept only as a trailing
"Technical detail:" for the audit. Wired into the per-criterion "site
inaccessible" note in `evaluator.py`.

**5. Smarter, better-laid-out report.** Added a grounded LLM executive summary
(`report/summary.py`, generated once in the background research thread in
`web/app.py`) — fed only the computed findings, told to restate them without
inventing facts or making a decision, optional/None-safe. Shown as a "Summary"
card on the PDF cover and web overview. Deterministic layout fixes in
`report.html`: cover trimmed to reliably fit one page (compact glance card,
tighter spacing), the "Needs your attention" list moved off the near-empty
cover page-2 onto the first content page, and the reference legend allowed to
flow across a page break (`pdf-allow-break`) instead of jumping whole to a
blank page. `ReportData` gained `research_note` and `executive_summary`.

Verified with no-cost local fixture renders (cover screenshot read back —
single page, summary reads naturally, explains the location gap) and 25 new
mocked tests (`test_error_messages`, `test_fee_match_diagnostic`,
`test_link_ranker`, `test_report_summary`, navigator 2-hop + dead-URL recovery
in `test_evaluator_smart_features`, plus `same_site_candidates`/`site_root` in
`test_link_discovery`, and PDF cover/attention/research-note in
`test_pdf_export`). Full suite: 115/115. **Live end-to-end verification on
Samples 4 & 5 still pending** (needs API credits — to be run against a local
server).

### Phase 5.7 — PDF "start page repeating" bug (2026-07-15)

User re-downloaded a report (92NY Coaching, run `16696789f8`) and reported the
PDF's start page looked repeated. Root cause: the Phase 5.5 cover page
(`.pdf-cover`, pdf_mode-only) shows participant/provider/category, source
site, verdict counts, appeal/fetch warnings, and the attention list — but the
Overview panel right after it rendered that same content a second time
unconditionally: `<header class="app-header">` (title/meta/verdict badges
again), the "Request at a glance" card (identical kv-grid again), the
appeal/fetch warning boxes again, and "What this report tells you" (same
summary sentence + same attention list again). In the interactive web view
this is correct — there's no cover page there, Overview is the first thing a
reviewer sees — but in `pdf_mode` it produced a near-duplicate second
"page 1." Fixed in `report.html` by wrapping `app-header`, the "Request at a
glance" card, the appeal/fetch warning boxes, and "What this report tells
you" in `{% if not pdf_mode %}` — all of that content already exists on the
cover page. The Overview panel in PDF mode now contains only what the cover
doesn't have: the Fee Comparison card and the How-to-read legend, under a new
`<h2 class="pdf-section-title">Fee Comparison &amp; Report Legend</h2>`
heading so the page still reads as its own section rather than starting
abruptly. Verified with a no-cost local fixture render (fabricated
`ReportData`, no API calls) reproducing the same shape as the reported bug —
page count dropped from the old duplicated-header layout and page 3 now
opens directly on "Fee Comparison & Report Legend" with no repeated header/
glance card. Added a regression test asserting each of those strings appears
exactly once (or zero times) in `pdf_mode` output
(`tests/integration/test_pdf_export.py::test_pdf_mode_does_not_repeat_the_cover_page_content`).
Full suite: 90/90 passing (was 89).

### Phase 5.6 — "Make it smarter" + report polish + full README rewrite (2026-07-15)

Following the Phase 5.5 PM evaluation, the user asked to actually build the
three report-polish items proposed there (cover page, denser print spacing,
the trailing footer-only page) plus the "Making the system smarter" ideas,
and to rewrite the README end-to-end for a non-technical reader. Two of the
"smarter" ideas involve real cost/latency tradeoffs (more Firecrawl/OpenAI
calls), so scope was confirmed with the user first via AskUserQuestion
before building: **bounded subpage re-fetch** (not aggressive, not skipped)
and **confidence-gated re-check** (not always-double-check, not
display-only) — both "Recommended" options.

**Confidence-gated self-consistency check** (`evaluation/llm_judge.py`,
`evaluation/evaluator.py`, `evaluation/models.py`): every `llm_judgment` call
now also returns a `confidence: high|medium|low` field (schema + prompt
addition) — an honest self-rating, not decorative. When a `found`/`not_found`
verdict comes back low-confidence, `_evaluate_web_criterion()` spends
exactly one more independent `judge_criterion()` call re-asking the same
question against the same page text; if the two disagree, the finding is
held at `needs_review` with a note explaining the disagreement instead of
picking one answer arbitrarily; if they agree, the result stands with a note
that it was double-checked. `Finding` gained a `confidence` field. This
directly targets the real inconsistency observed live across two separate
Sample 10 runs earlier in this session (4/8 confirmed, then 2/8 confirmed
against materially the same page).

**Bounded subpage rescue** (`research/link_discovery.py` new,
`research/models.py`, `research/firecrawl_client.py`,
`research/playwright_client.py`, `evaluation/evaluator.py`): `PageCapture`
now carries `links: list[str]` (Firecrawl's `links` format, or Playwright's
`a[href]` query for the fallback path). If a fee/price/schedule-type
criterion (matched generically by keyword in the criterion id/question —
"fee", "price", "schedule" — not a per-category list) is still Needs Review
after the homepage, `_try_subpage_rescue()` tries up to 2 same-site,
keyword-ranked candidate links (via the new `find_candidate_subpages()`),
re-evaluates only the still-unresolved criteria against the combined text
of the original page + the followed page, and stops early once everything
resolves. Wrapped so a bug in this bonus pass can never take down the
primary (already-good) single-page results. Only costs extra fetches on
applications that actually need it — a fully-resolved homepage triggers zero
extra Firecrawl/Playwright calls.

**A real bug this caught live, fixed the same session:** the first live
verification run against Sample 10 showed the rescue pass wasting one of
its two bounded attempts on `https://graciebarra.com/#modal-bookclass` — a
same-page modal anchor, not a different page at all, fetching identical
content to the homepage already checked. Fixed in `link_discovery.py`: URL
identity for dedup/exclusion is now compared ignoring fragment and query
string, so a `#anchor` variant of the already-fetched page is correctly
treated as "the same page," not a fresh candidate. Regression test added
(`test_excludes_same_page_anchor_of_the_fetched_page`).

**PDF cover page** (`web/templates/report.html`): a new `pdf_mode`-only
`.pdf-cover` section, forced onto its own first page (`break-after: page`),
showing participant/provider/item/category/website/fee, a large 4-box
verdict-count grid, the appeal denial-reason callout if present, a
recommendation-neutral one-sentence summary, a "Needs your attention" list
(reusing the existing `attention_items` property), and a footnote pointing
to the detailed pages that follow. Lets a reviewer see the whole shape of a
case before reading eight-plus individual findings.

**Denser print-mode spacing and fewer forced blank pages**
(`web/templates/report.html` `@media print` block): tightened `.card`
padding/margin, `.finding-body` padding, `.answer-compare`/`.finding-quote`
margins, and the evidence-thumbnail crop height for print specifically
(screen view untouched) — the screen layout's generous whitespace is tuned
for comfortable reading, not maximum useful content per printed page. Also
shrank the closing footer's padding/font-size since a shorter trailing block
needs less remaining page space to avoid the browser's orphan/widow rule
bumping it onto its own near-blank page (a CSS print-pagination quirk, not
fully eliminable without a fragile hack — reduced, not solved outright, and
noted as such rather than overclaimed).

**Root-cause note on a hypothesis that turned out wrong:** before touching
CSS, suspected `write_report_pdf` never called
`page.emulate_media(media="print")`, so `@media print` rules might never
engage. Verified empirically with a no-cost local render (fabricated
`ReportData`, no API calls) before and after adding the call — **output was
byte-identical**. Chromium's `page.pdf()` already applies print media by
default in this Playwright version; the earlier-suspected "blank strip on
the right" was the browser's own PDF-viewer thumbnail sidebar, not a real
bug in the PDF. Added the explicit `emulate_media` call anyway (harmless,
documents intent, guards a future Chromium/Playwright behavior change) but
did not report it as a fix for something that was never actually broken —
important not to over-claim just because a plausible-sounding theory was
available and cheap to try.

**Fixture-locked regression tests** for the two adversarial samples the
brief calls out by name, loading the REAL committed
`config/checklists/*.yaml` files (not copies), so a future edit that breaks
either case fails CI immediately:
- `tests/unit/test_exclusion_list_regression.py` — Sample 07's "Laptop
  computer" hits HRI's "Computer Hardware" exclusion; Sample 08's "Weighted
  Blanket" clears OTPS's (different) exclusion list; an explicit
  cross-wiring guard proves a laptop is excluded under HRI but NOT under
  OTPS's list (which doesn't mention computers).
- `tests/unit/test_evidence_provenance_regression.py` — a mocked
  hallucinating LLM (confident "found" + a fabricated quote never on the
  real page) produces a Finding correctly discarded down to `needs_review`,
  quote cleared, at the full `run_evaluation()` level — not just the
  `is_quote_grounded()` primitive already covered in `test_text_utils.py`.
- `tests/unit/test_evaluator_smart_features.py` (4 tests) and
  `tests/unit/test_link_discovery.py` (6 tests) — the two new "smarter"
  behaviors, everything mocked, no real API calls.

**Verified live end-to-end** (not just fixture tests): started a temporary
local server, ran real Sample 10 through the actual upload → confirm →
research → export flow twice — once before the fragment-URL fix (caught the
`#modal-bookclass` waste), once after (clean: followed `/classes/`,
correctly stayed Needs Review since that page genuinely doesn't publish
fees either — the honest, correct outcome, not a regression). Read every
page of both resulting PDFs. Confirmed: cover page renders correctly with
accurate counts, denser spacing, no forced-blank sections, subpage-rescue
progress messages appear in the live progress feed
("Checking a linked page for missing details (...)"), and no fabricated
results were introduced by any of this session's changes.

**Full README rewrite** (everything above the "Appendix: original challenge
instructions" section, which is preserved verbatim per its own precedence
rule): restructured around a narrative "how it thinks" walk through the
pipeline stage-by-stage explaining the deterministic-vs-LLM split and why
it exists; a dedicated "Why these models and tools" section justifying each
external dependency (OpenAI GPT-4o, Firecrawl, Playwright, pdfplumber,
Claude Code) by the specific job it does, not just naming them; an
"Evidence: the load-bearing idea" section foregrounding the
never-Found-without-evidence invariant as the single most important design
decision in the project; a "Made it smarter" section documenting this
phase's two additions and their bounded-cost rationale; a "Report
formatting" section covering the cover page/spacing/footer work; and a
"Where this goes next: a production roadmap" section that honestly proposes
(not implements) the items from the Phase 5.5 PM evaluation's "what's
missing" list — per-category regression coverage, a real datastore/task
queue, PHI-handling controls, generalized multi-page research, monitoring,
and scheduled re-verification — framed as deliberate future scope decisions
for a team to make, not silently deferred. `docs/limitations-and-assumptions.md`
updated to match (single-page-research limitation now describes the bounded
rescue pass accurately; LLM non-determinism note updated to mention the
confidence-gated mitigation).

Full pytest suite: 89/89 passing (was 74; +15 across this phase's new test
files). Nothing committed to git.

### Phase 5.5 — PDF pagination polish, PM evaluation (2026-07-15)

User asked for a PM-level evaluation of the whole build plus concrete
improvements to make the exported PDF look properly professional (their
words: "readable and well formatted... without too much blank space").

**Investigated, then ruled out, a plausible-sounding hypothesis.** Suspected
`write_report_pdf` never called `page.emulate_media(media="print")`, so the
`@media print { .panel { max-width: 100%; } }` override (and everything else
print-only) would never engage, leaving every panel capped at its 760px
screen width and wasting ~35-40% of every Letter page as blank margin.
Verified empirically with a no-cost local render (fabricated `ReportData`,
no API calls) before and after adding the `emulate_media` call — **the
output was byte-identical**. Conclusion: Chromium's `page.pdf()` already
applies print media by default in this Playwright version; the "blank
strip" visible in earlier screenshots was the browser's own PDF-viewer
thumbnail sidebar, not a real margin bug in the PDF. Added the explicit
`emulate_media("print")` call anyway (harmless, makes the intent explicit,
guards against a future Playwright/Chromium behavior change) but did not
report it as a "fix" for something that was never actually broken —
important not to over-claim to the user just because a plausible theory
was available.

**Real, verified pagination bug: every section forced its own fresh page
regardless of how little content followed.** `.panel.pdf-page-break {
break-before: page; }` was applied to Findings, Evidence, Internal Checks,
*and* Review & Export — so whenever one of the latter three had modest
content (a handful of evidence thumbnails, a short completion-status card),
it still burned an entire page, most of which sat blank. Confirmed with the
same no-cost fixture: before the fix, a report with just 2 findings and no
evidence produced 6 pages, with page 4 being *99% blank except for the
single word "Evidence."* Fix: `pdf-page-break` (hard page-break) now applies
only to the Findings section — the one genuinely long section that
deserves its own fresh start after the short Overview. Evidence, Internal
Checks, and Review & Export now flow continuously right after Findings ends,
each still clearly demarcated by a `.pdf-section-divider` (top border +
generous margin) instead of a wasted blank page. Re-ran the identical
fixture after the fix: same content now fits in **4 pages, not 6**, with no
mostly-blank pages anywhere. Re-verified against a real, live Sample 10 run
(real OpenAI + Firecrawl calls): Evidence/Internal Checks/Review & Export
now share pages 9-11 with clean divider lines instead of each starting a
near-empty page — down from 13 pages in the original user-reported run to
12, with real findings content (Sample 10's fee/schedule genuinely absent
from the site, so those items are legitimately Needs Review — nothing here
was changed by these polish fixes, only presentation).

**One minor residual noted, not chased further:** the report's closing
footer occasionally lands alone on a near-blank trailing page when the last
section ends close to a page boundary. Judged not worth a fragile CSS
workaround for the size of the benefit — flagged for a future pass if it
recurs annoyingly on more samples.

Full pytest suite: 74/74 passing throughout (no test changes needed — this
was pure CSS/template polish, verified via direct PDF generation and
reading the rendered pages, not automated assertions, consistent with this
project's established practice for print/visual output).

### Phase 5.4 — Second QA pass on Sample 10, report-clarity polish (2026-07-15)

The user re-ran Sample 10 after the Phase 5.3 cookie-banner fix and evaluated
the fresh report + PDF specifically against the brief's evaluation question
"Report clarity — could a non-technical reviewer act on it immediately?".
The cookie banner was gone (fix confirmed working), but two more real
defects surfaced from actually reading every page of the generated PDF:

1. **Blank/gray placeholder evidence images.** Two of four targeted crops
   ("course/credit description," "class description (non-clinical)")
   rendered as empty gray boxes in the exported PDF, even though the exact
   same crop function returned a perfectly good image when called directly
   (confirmed by re-running `screenshot_element_by_text` live and reading
   the bytes — navy quote block, fully readable). Root cause: both evidence
   `<img>` tags in `report.html` used `loading="lazy"`, which is correct for
   the interactive web view but wrong for the PDF path — `write_report_pdf`
   unrolls every tab into one long linear document and only waits for
   `networkidle` before calling `page.pdf()`; a browser never fires the
   network request for a lazy image sitting far below the initial viewport,
   so `networkidle` is satisfied without it ever loading, leaving a blank
   placeholder baked into the PDF. Fix: `loading="lazy"` is now conditional
   on `{% if not pdf_mode %}` in both places it appears (Findings-tab
   thumbnail and Evidence-tab full image) — eager-loads in PDF mode only.
2. **Redundant, and for "Found" statuses self-contradictory, duplicate
   evidence per finding.** Every finding card was showing *two* screenshots:
   the shared whole-page capture (added unconditionally to every finding)
   plus a second attempt via `capture_targeted()` — and when that second
   attempt failed to isolate the quote as a literal DOM element (common when
   the LLM's quote is a close paraphrase, not verbatim page text), the old
   fallback fabricated a *second* whole-page image captioned "Context
   reviewed — no public X clearly visible on the page," directly
   contradicting the finding's own "Found" badge sitting right above it.
   This also roughly doubled embedded-image count, worsening PDF page-break
   behavior (large blank gaps from `break-inside: avoid-page` pushing
   oversized image blocks to the next page as a unit). Fix: `capture_
   targeted()` (`evidence/capture_service.py`) now returns `EvidenceItem |
   None` — `None` when no real crop can be produced, instead of fabricating
   a second whole-page fallback. The caller (`evaluation/evaluator.py`) now
   attaches exactly one evidence image per finding: the real targeted crop
   when one exists, otherwise the single shared whole-page evidence object
   (same instance already used elsewhere, no new file, no confusing extra
   caption).

**Verified with a real, live end-to-end run** (not just re-reading the
user's screenshots): started a temporary local server, uploaded Sample 10
for real, waited for real OpenAI + Firecrawl calls to finish, downloaded the
resulting PDF via the real export route, and read every page. Confirmed: no
cookie banner anywhere, no blank/gray placeholder images (both previously-
blank crops now show their real navy quote-block content), no duplicate or
contradictory evidence under any finding (each finding shows exactly one
image), and the PDF is now 11 pages (down from 13) with no more large
mid-page blank gaps from cascading page-break rules. Full pytest suite:
74/74 passing (no new tests needed — this pass's fixes are exercised by the
existing `test_pdf_export.py` and `test_cookie_banner_suppression.py`
coverage; the live end-to-end run was the primary verification method here,
consistent with this project's established practice that visual/print
output must be visually re-inspected after a fix, not just re-tested at the
unit level).

### Phase 5.3 — User QA pass on Sample 10 (Appeal, Gracie Barra), cookie-banner evidence bug (2026-07-15)

The user manually ran the tool against `Sample-10---Appeal-Gracie-Barra-Jiu-Jitsu.pdf`
through the real UI and reviewed the full report + exported PDF, then evaluated
the output against the brief's §5/§6/§8 requirements directly.

**PM evaluation of the run itself (no code issue):** the appeal-mode logic
worked as designed — the original denial reason is quoted and findings are
explicitly framed against it; 4 of 8 website-verifiable items honestly landed
on Needs Review (no published fee, no schedule, no OPWDD-pricing statement)
rather than guessing, which is the brief's single most important bar (§5 "no
guessing on the checklist"); all §6 report sections are present (request at a
glance, fee comparison with plain-language verdict, per-criterion findings
with evidence + quotes, Internal Checks clearly separated as human-only).

**Real bug found and fixed — targeted evidence screenshots showed a cookie
banner instead of the actual proof.** 3 of 4 targeted crops
(`open_to_public`, `subject_area`, `course_credit`) displayed graciebarra.com's
cookie-consent banner text ("This website uses cookies...") instead of the
quoted proof line, even though the quote itself in the report text was
correct. This directly undermines the brief's §6 evidence requirement ("a
focused screenshot showing exactly where the proof appears") — the report's
words were right but the attached image didn't back them up.

Root cause (confirmed by reading the code, not guessed — see Key Learnings
for the full writeup): nothing anywhere in the codebase ever dismissed or
hid a cookie-consent banner before taking a screenshot. `screenshot_element_
by_text()` (`research/playwright_client.py`) correctly located the real proof
text and scrolled to it, but `locator.screenshot()` captures *composited
viewport pixels*, not an isolated DOM render — so a still-visible fixed-
position banner painted on top got baked into the crop regardless of which
element was targeted. Confirmed via `grep -rniE "cookie|consent|dismiss|
accept|banner" src/` returning zero matches before the fix.

**Fix:** added `_suppress_cookie_banners(page)` in `playwright_client.py` —
best-effort click of a common "Accept"-style button (short timeout, silently
skipped if absent), followed by injected CSS that force-hides any remaining
consent-banner container by common id/class patterns (`cookie`, `consent`,
OneTrust/Cookiebot/Osano/Quantcast selectors) — so even non-standard banners
that don't match a clickable label can't visually intrude. Called before
every capture in both `fetch_via_playwright` (whole-page fallback) and
`screenshot_element_by_text` (targeted crops). Firecrawl's primary whole-page
path (`firecrawl_client.py`) got the equivalent fix via its `actions` param —
an `ExecuteJavascriptAction` that injects the same hide-CSS before Firecrawl
captures its screenshot/markdown, so the banner text can't pollute the
extracted page text either, not just the image.

Verified live against the real graciebarra.com (not just a unit test): both
`screenshot_element_by_text()` and `fetch_via_firecrawl()` re-run after the
fix, screenshots read back with the Read tool — clean in both cases, no
banner artifact. Added `tests/integration/test_cookie_banner_suppression.py`
(2 tests, local HTML fixture, no live network) as permanent regression
coverage: one asserts the banner element becomes non-visible after
suppression, one asserts a targeted crop of unrelated text doesn't contain
the banner's distinctive color. Full suite: 74/74 passing (was 72; +2).

### Phase 5.2 — PDF report export (2026-07-15)

User question: why does the tool export HTML and JSON but not PDF, given
the brief's §6 asks for "a shareable report... bundled so a reviewer can
save and share them"? Re-read Project-Brief.pdf §6 directly (not the Phase 1
paraphrase). Conclusion: HTML/JSON were never meant to *be* "the report" —
JSON is structured data for machine/audit-system consumption, and the
static HTML was a lightweight snapshot of the live reviewer view. Neither is
as strong a "hand this to a non-technical reviewer" artifact as a single,
well-formatted, printable PDF, especially in a domain where every other
document in this workflow (the application itself) is already a PDF.

**Product decision locked with the user:** PDF becomes the primary/
recommended download; HTML and JSON stay available as secondary options
(tucked under a "More formats" disclosure), nothing removed.

**Implementation** (`report/generator.py::write_report_pdf`): renders the
exact same `report.html` template with a new `pdf_mode=True` flag (one
source of truth for layout, no second template to maintain), then uses
Playwright's `page.pdf()` — already a hard dependency of this project for
browser automation, so no new PDF library was added. `pdf_mode` unrolls
every tab into one linear, paginated document instead of hiding all-but-
one behind JS (a PDF has no clickable tabs): removes the sidebar, strips
all interactive-only chrome (filters, search, regenerate, reviewer-action
forms — already gated by the existing `interactive` flag), forces every
`<details>` (findings, "how to read this report") open since nothing is
collapsible in print, and adds `break-inside`/`break-after` print-CSS rules
so cards and evidence images don't fragment mid-element across a page
boundary. New route: `GET /applications/{id}/export/report.pdf`. The ZIP
package now embeds `report.pdf` alongside the existing contents.

**A real, non-obvious bug found and fixed during this pass** — see Key
Learnings: a Chromium print-engine flexbox-fragmentation quirk left stray
orphaned chevron characters floating at page breaks in the Findings tab.

Verified by generating a real 12-page PDF from a live Sample 01 run and
visually inspecting every page (not just checking file size/status code) —
confirmed correct pagination, all tabs' content present, evidence images
embedded, and (after the fix) clean page breaks with no visual artifacts.
Added `tests/integration/test_pdf_export.py` (3 tests, no network calls —
local Playwright render only) as permanent regression coverage. Full suite:
72/72 passing (was 69; +3 for PDF export tests).

### Phase 5.1 — User QA pass on Sample 07, bug fixes (2026-07-15)

The user ran their own manual QA against Sample 07 (HRI Laptop) through the
actual UI and reported findings with screenshots. Results:

- **Real bug, fixed**: "Mark completed"/"Mark reviewed" stayed visible and
  clickable after already being clicked, with no visible state change and
  no way to undo — a second click was a silent no-op. Fixed in both the
  Findings and Internal Checks tabs (`web/templates/report.html`): the
  button now hides once `f.reviewed` is true, replaced by "Restore system
  result"/"Restore original" (if overridden) or a new "Undo (mark as not
  reviewed/completed)" action (if plainly marked reviewed, not overridden)
  — both reuse the existing generic `/restore` route, which already handled
  the "just reset `reviewed`, don't touch status/note" case correctly since
  `original_status` stays `None` for a plain mark-reviewed. Added
  `tests/integration/test_reviewer_action_buttons.py` (4 tests, no LLM/
  network calls) as a permanent regression test, and additionally verified
  live via real Playwright browser clicks (button really disappears/
  reappears across a real page reload, zero console errors).
- **Real cosmetic bug, fixed**: the Overview "Request at a glance" card
  always rendered a "Provider" row and a "Submitted fee" row even for
  categories whose form has no such field (HRI/OTPS have no distinct
  provider-name field — only an item + a link) — showing a confusing blank
  "—" instead of a genuinely absent field. Both rows are now hidden when
  the value is `None`, matching the pattern already used for "Source
  website" elsewhere on the same card.
- **Not a bug — confirmed via a clean, extension-free Playwright pass**:
  the "Unchecked runtime.lastError: The message port closed before a
  response was received" console messages the user saw are Chrome
  extension noise (the user's screenshot shows an active "Ask Gemini"
  extension in the toolbar), not from this app — a real browser launched
  with zero extensions loaded produced zero console errors across the
  same upload → confirm → report flow.
- **Not a bug — working as designed**: the Amazon product-page screenshot
  in the evidence viewer shows Amazon's bot-check interstitial ("Click the
  button below to continue shopping"), not the actual laptop listing.
  Amazon blocked the fetch; the tool honestly reported Needs Review rather
  than fabricating product details — exactly the documented, intended
  behavior for anti-bot-protected sites (see
  `docs/limitations-and-assumptions.md`), not something to "fix" by trying
  to defeat Amazon's bot detection.
- The exclusion-list finding ("Not Found" — laptop vs. "Computer Hardware")
  worked correctly regardless of the blocked product page, confirming the
  Phase 3 fix (exclusion checks don't require a successful fetch) holds up
  under real, uncooperative-website conditions, not just the happy path.

Full pytest suite: 69/69 passing (was 65; +4 for the button-state
regression test).

### Phase 5 — QA and submission readiness — DONE (2026-07-15)

The original Phase 1 plan's "Phase 4 — QA and submission readiness" (renumbered
to Phase 5 here since the Manage Checklists UI took the Phase 4 slot). No new
product code — closed out the required non-code deliverables and did a
literal, line-by-line walkthrough of the actual brief (re-read
`docs/Project-Brief.pdf` in full rather than relying on the Phase 1 plan's
paraphrase of it, to ground this in the literal grading criteria):

- **`docs/acceptance-criteria-checklist.md`** (new) — every item in the
  brief's §8 (10 acceptance criteria), §9 (deliverables), and §10
  (constraints/data-handling) mapped to the concrete file/behavior that
  satisfies it, plus a repo-hygiene checklist. Two items are explicitly
  marked as the user's own remaining action, not something the agent can
  do: pasting the real AI-CONVERSATION.md transcript, and making the repo
  public/pushing/submitting.
- **`AI-CONVERSATION.md`** — replaced the placeholder's "Tools & Models
  Used" section with the real, factual list (Claude Code / Sonnet 5 as the
  build agent; GPT-4o as the in-product model; Firecrawl; Playwright;
  pdfplumber), correctly distinguishing "built with" vs. "product calls at
  runtime." The actual conversation transcript is intentionally left as a
  clearly-marked placeholder — the agent cannot fabricate a real exported
  session on the user's behalf without defeating the point of the
  requirement (it must be their genuine transcript, including real dead
  ends and corrections, not a cleaned-up narrative written after the fact).
- **Full repo-wide secret scan** (not just tracked-candidate files as in
  earlier passes) — zero matches for API-key patterns anywhere in the
  working tree, including untracked files. `.env` confirmed git-ignored.
- **PHI scan** — grepped all committed sample output for SSN/phone/email
  patterns; none found beyond the synthetic agency addresses already in the
  provided sample PDFs.
- **Verified zero tool-emitted approve/deny language** — grepped
  `src/preapproval_tool/` for approval/denial wording, excluding the form's
  own printed "For office use only" fields and internal-criterion questions
  that literally ask about budget *approval status* (a different, correct
  use of the word) — confirmed the tool itself never emits a verdict beyond
  Found/Not Found/Needs Review/Internal.
- **README**: renamed "Status — what's implemented vs. pending" to "Status"
  (nothing is actually pending anymore), added a pointer to the new
  acceptance-criteria checklist doc.

Full pytest suite still 65/65 passing (no code changed this phase, only
docs). Nothing committed to git — this phase deliberately stopped short of
the two remaining actions above, which only the user can take.

### Phase 4 — Non-technical "Manage Checklists" UI — DONE (2026-07-15)

The brief requires: checklists be config-driven (already true — verified zero
hardcoded category strings anywhere in `src/`), a non-engineer be able to add
a new category by supplying a new checklist, and the README document how.
Config-driven + documented was already true, but hand-authoring YAML with
`check_type` enums and a `caps` dict syntax is still engineer-legible, not
truly something to hand to a non-technical FI Coordinator. This phase adds a
web UI so a non-technical user can add/edit a category through a form
instead of YAML.

**Product decisions locked with the user before building (2026-07-15):**
1. **Draft/review workflow, not immediate-live.** A non-technical user's
   new/edited checklist saves as a draft under `data/checklist_drafts/` and
   never touches `config/checklists/*.yaml` until an engineer/lead reviewer
   explicitly clicks "Publish." Reasoning: this config directly controls a
   compliance tool's Found/Not Found judgments — a subtly wrong config must
   not silently go live the moment a non-expert clicks Save. A draft can be
   tested against a real sample PDF before publishing.
2. **No new auth on this page.** Matches the rest of this build, which has
   no login system at all (single-operator/local-demo scope per
   `docs/limitations-and-assumptions.md`) — adding auth to just this one
   page would be inconsistent scope creep for this exercise.

**What shipped:**
- `checklist_engine/draft_builder.py` — converts a plain-language wizard
  dict (no `check_type`/`verifiable` vocabulary shown to the user) into a
  schema-valid checklist config dict (`validate_wizard`), and back
  (`wizard_from_checklist_config`, for editing an existing live category by
  opening it pre-filled). Every field type, web-check kind
  (general judgment / price comparison / exclusion list), and
  internal/document distinction is expressed as a plain-language choice —
  the generated YAML is shown on the review page for anyone technical who
  wants to see it, but is never required reading to author a category.
- `checklist_engine/draft_store.py` — disk-backed JSON drafts under
  `data/checklist_drafts/` (gitignored) — deliberately NOT under
  `config/checklists/`, so a future change to the loader's glob pattern can
  never accidentally treat an unpublished, unreviewed draft as live config.
- New routes on the existing FastAPI app (no separate service): list view
  (`/manage-checklists`), wizard (`/manage-checklists/new`,
  `/manage-checklists/edit/{category_id}` pre-filled from a live category,
  `/manage-checklists/drafts/{id}/wizard` pre-filled from a saved draft),
  save-draft (always saves whatever was entered, even if incomplete — only
  *publishing* is gated on validity), test-against-a-sample-PDF (builds a
  throwaway in-memory `ChecklistConfig` from the draft and runs the same
  `extract_fields`/`run_evaluation` pipeline as a real application, without
  ever touching `config/checklists/`), publish (writes the YAML, clears
  `load_all_checklists()`'s `lru_cache`, deletes the draft), discard.
- Publish safety checks: refuses to publish if the resulting `category_id`
  already belongs to a different live category (name collision); if editing
  an existing category and the ID is unchanged, publishing overwrites that
  category's file in place (this is the "update an existing category" path).
- `templates/checklist_wizard.html` — a single-page, vanilla-JS wizard
  (no new frontend framework, consistent with the rest of the build):
  repeatable rows for identifying phrases / fields / questions, with
  conditional plain-language sub-sections per question (price-cap inputs,
  exclusion-term list builder, "why can't this be checked" explanation) —
  built with `<template>` elements + DOM cloning, matching the pattern
  already used for evidence-lightbox delegation elsewhere in this codebase.
- `templates/checklist_draft_review.html` — plain-English criterion summary,
  generated YAML, a live "test with a sample PDF" action, and
  Publish/Edit/Discard.
- `load_all_checklists()`'s `lru_cache` is cleared on publish so a newly
  published category is picked up without a server restart.
- Tests: `tests/unit/test_draft_builder.py` (8 tests — valid-wizard
  round-trip, exclusion terms carry through, price-cap mode mapping,
  plain-language error messages for missing name/questions/exclusion terms,
  duplicate-question-text still gets unique criterion IDs, and a full
  round-trip of an existing hand-authored category through the wizard and
  back) and `tests/integration/test_manage_checklists_routes.py` (7 tests,
  isolated via monkeypatched `CHECKLISTS_DIR`/`draft_store` so nothing
  touches the real config directory — create/review/publish/discard, an
  incomplete draft blocking publish with plain-language errors, publish
  rejecting a category-ID collision, and editing-and-republishing an
  existing category in place).
- Live-verified via Playwright against the real running server (not just
  the isolated route tests): the full wizard flow — dynamic field/question
  rows, the exclusion-term list builder, the review page's plain-English
  summary and generated YAML, and discard — with zero console errors. See
  Key Learnings for a real JS bug this live pass caught that the route-level
  tests structurally could not (they don't execute JavaScript).

Full pytest suite: 65/65 passing (was 50; +15 for this phase). Nothing
committed to git; drafts directory is gitignored. `config/checklists/`
still has exactly the 7 real categories — the live-verification pass's test
category was discarded, never published.

### Phase 3 — DONE (2026-07-15, approved to start after Phase 2.2 sign-off)

All 7 checklist categories now exist and all 10 samples have run live
end-to-end (real OpenAI + Firecrawl calls):

| # | Sample | Category | Result summary |
|---|---|---|---|
| 01 | GallopNYC | community-classes | 6 found / 0 not found / 2 needs review (baseline) |
| 02 | Gracie Barra | community-classes | 3 found / 0 / 5 needs review — gated pricing, honestly Needs Review, no guessing |
| 03 | 92NY Parenting | coaching | 1 found / 0 / 1 needs review |
| 04 | Planet Fitness | memberships | 0 found / 0 / 3 needs review — national gyms page didn't show location-specific pricing; correctly not guessed |
| 05 | Brooklyn Museum | memberships | 0 found / 0 / 3 needs review — `brooklynmuseum.org/join` now 404s (real site drift since sample authoring); correctly reported "Needs Review — site inaccessible", not fabricated |
| 06 | HRI Grab Bar | hri | 1 found / 0 / 2 needs review — exclusion check correctly clears it; Amazon page fetch didn't yield readable product text, honestly Needs Review rather than guessed |
| 07 | HRI Laptop | hri | **0 found / 1 not found / 2 needs review — the exclusion-list trap works**: "Laptop computer" deterministically matches "Computer Hardware" |
| 08 | OTPS Weighted Blanket | otps | 1 found / 0 / 1 needs review — correctly clears the (different) OTPS exclusion list |
| 09 | LaGuardia CC | transition-program | 1 found / 0 / 3 needs review — fee-cap check correctly passes ($300 form fee within $350 cap); document-only staff-screening criterion renders correctly |
| 10 | Appeal (Gracie Barra) | appeals | **4 found / 0 / 4 needs review — the hardest case works as designed**: denial-reason banner renders, and `published_fees` still comes back Needs Review — the tool does not let the appellant's non-web rate sheet upgrade a website finding it can't independently verify |

New checklist configs: `coaching.yaml`, `memberships.yaml`, `hri.yaml`,
`otps.yaml`, `transition-program.yaml`, `appeals.yaml` (mirrors
`community-classes.yaml`'s 8 web-verifiable criteria per the brief's "appeal
re-runs the base category" design, plus one appeal-specific internal
criterion — `appeal_evidence_provenance` — that explicitly tells the
reviewer any non-web evidence in the appeal justification needs independent
review).

Engine changes required (all generic, no category-specific code):
- `evaluator.py`: `exclusion_list`-type criteria no longer require a
  successful page fetch to be evaluated (see Key Learnings) — they're a pure
  form-data check (item name vs. configured list) and shouldn't be blocked
  by a dead/unreachable product link.
- `fee_match.py`: added a cap-ceiling comparison mode
  (`caps: { max: N }`) alongside the existing tolerance-based exact-match
  mode (`caps: { tolerance_pct: N }`), used by Coaching's $111/class and
  Transition Program's $350/course caps.
- `checklist_schema.json` / `evaluate_rule` already supported
  `verifiable: document` from Phase 1 — Transition Program's staff
  background-screening criterion is the first one to actually use it.
- Added `tests/unit/test_fee_match_cap.py` and 4 new schema/integration
  tests in `tests/schema/test_checklist_schema.py` (all 7 categories load,
  every category has ≥1 web and ≥1 internal criterion, appeals references
  its base category, HRI/OTPS both have populated exclusion lists).

Full pytest suite: 50/50 passing (was 42; +8 for the new fee-cap and
category-coverage tests). Nothing committed to git yet — awaiting explicit
approval per standing instruction.
- README overhaul reflecting the final reviewer journey
- Full pytest suite (only partially covered so far — see below)

### Phase 2.2 checklist (PM feedback round 2, 2026-07-15) — ALL DONE
- [x] Design system: single white/blue/navy theme, dropped the OS-driven
  `prefers-color-scheme: dark` override in both `report.html` and the shared
  `_style.html` partial (this is why prior screenshots showed dark — the
  reviewer's OS was in dark mode and the CSS silently followed it)
- [x] Header redesign: compact product bar ("Pre-Approval Verification" +
  "New review" action) above the existing report header
- [x] Findings collapsed/expanded split: new LLM-provided `short_note` field
  (schema-validated, `evaluation/models.py::Finding.display_short_note`)
  shown in the collapsed summary; full reasoning only in the expanded body
- [x] Reasoning calibration: `llm_judge.py` system prompt now instructs (a)
  judging a criterion's core claim independently of a secondary caveat
  instead of downgrading the whole finding, (b) preferring a substantive
  descriptive quote over a bare page heading/title, (c) evaluating the
  specific named offering, not the organization as a whole, when a provider
  runs multiple distinct programs. Verified live: `open_to_public` and
  `not_clinical` moved from Needs Review to Found on Sample 01 with accurate
  caveat language, without any per-sample hardcoding.
- [x] Evidence honesty: replaced the misleading "(full page — see
  highlighted text below)" fallback label (implied highlighted text that
  didn't exist) with "Context reviewed — no public {fact} clearly visible on
  the page" whenever a targeted crop could not be isolated
- [x] Reviewer workflow: Internal Checks tab now has mark-completed,
  confirm/challenge-with-note, and a "document checked" field, using the
  same generic override/mark-reviewed/restore routes as Findings (the
  `Finding`/`FindingStatus` model already supported `"internal"` as a
  status, it just wasn't wired into that tab). Added
  `internal_reviewed_count`/`total_internal`/`overall_reviewed_count`/
  `overall_total` to `ReportData`, surfaced as X of 8 / X of 12 / X of 20.
- [x] Review & Export: draft vs. completed-package labeling driven by
  `ReportData.is_review_complete`; added
  `unconfirmed_evidence_findings` as a pre-export completeness check
  surfaced in the UI (not just buried in `validation_issues` JSON)
- [x] Responsive fix: found and fixed the actual cause of the "awkward
  navigation around 799px" — see Key Learnings below
- [x] QA: full pytest suite (42 unit/schema/security) + the live E2E
  acceptance test, both passing; live Sample 01 run + Playwright-driven
  screenshot check at 360/390/430/768/799/1024/1280/1440px (no overflow, no
  console errors); secret scan clean; `.env` confirmed untracked

#### Work sessions
- 2026-07-15: Phase 2.2 (UI polish, reasoning calibration, reviewer
  workflow completeness, QA) implemented in one session per PM feedback
  round 2. Sample 01's committed package regenerated against the final UI.
  Nothing committed to git yet — awaiting explicit approval per standing
  instruction.

### Phase 2.A checklist (from PM feedback, 2026-07-15) — ALL DONE
- [x] Step 1 — Audit
- [x] Step 2 — Information architecture (5-tab workspace)
- [x] Step 3 — Non-technical Overview screen
- [x] Step 4 — Finding card progressive disclosure + filters + search
- [x] Step 5 — Evidence model fixes (grounding validation, honest labeling, evidence IDs)
- [x] Step 6 — Evidence viewer overhaul (zoom, download, focus trap)
- [x] Step 7 — Internal checks: criterion-specific explanations, grouped
- [x] Step 8 — Reviewer actions: persist overrides across regenerate, audit history, progress indicator
- [x] Step 9 — Real research progress screen
- [x] Step 10 — Extraction confirmation page improvements
- [x] Step 11 — Review & Export section + package download
- [x] Step 12 — Design system / tokens
- [x] Step 13 — Responsiveness pass (verified 390/768/1280px)
- [x] Step 14 — Accessibility pass (practical WCAG 2.2 AA target — see docs/ux-and-evidence-integrity.md for what was/wasn't covered)
- [x] Step 15 — Polish bugs (favicon, markdown leakage, console errors, onclick/tojson bug)
- [x] Step 16 — Security/data-integrity test coverage
- [x] Step 17 — Test suite + Sample 01 acceptance E2E test (42 unit/schema/security + 1 e2e, all passing)
- [x] Step 18 — Documentation (README, UX/evidence-integrity doc, limitations doc)

Not independently covered in this pass (call out honestly rather than
claim otherwise): no automated axe-core/Lighthouse accessibility audit; no
IPv6-specific SSRF test beyond `::1`; prompt-injection defense is
architectural (untrusted-data framing + schema validation) and was not
re-verified with a live adversarial-page test in this session.

#### Work sessions
- 2026-07-15: Full Phase 2.A implementation completed in one session —
  see the "What shipped" list above. Sample 01's committed package
  regenerated against the new UI.

---

## 6. Key Learnings

*(Append new entries at the top. Format: what happened, what we changed, what
we should avoid next time.)*

### 2026-07-15 — Reaching a fact is not the same as confirming it; and silence is not evidence

Two adjacent lessons from the final QA pass. (1) The smarter navigator made a
new *accuracy* mistake the old dumb one couldn't: it reached a real price page
and confirmed a Newark branch's $15 as the applicant's fee — but the form never
said Newark. Getting *a* number is not getting *the* number; whenever a value
is location/tier-scoped and the form doesn't pin the scope, the honest output is
Needs Review + a labelled example, never a confirmation. (2) The model kept
marking "must be NO" negatives (no college credit, not clinical) as Found off a
*silent* page — treating absence as proof. The durable fix wasn't just a better
prompt; it was a deterministic backstop (a website Found must carry a readable
targeted crop of the actual proof — silence produces no quote, no crop, so it
can't be Found). Prompts reduce the rate; a code invariant sets the floor. Also:
a cross-config regression test earned its keep immediately by catching a
copy-paste drift (`form_question` lost between the base and appeal configs) that
no one would have spotted by eye — which is why the appeal now *reuses* the base
criteria at load time instead of mirroring them.

### 2026-07-15 — "Can't find the price" is usually a navigation/ambiguity problem, and the honest fix is to explain the gap, not to guess

Two samples looked like the same bug ("can't scrape the price") but had three
different root causes: the price was two links deep behind a location picker
(PF), a good link was invisible to keyword ranking (Brooklyn's
`/become-a-member`), and the form's own URL was dead so rescue never ran
(Brooklyn's `/join`). The lesson: a flat "Needs Review — could not locate a
price" hides *why*, and the "smart" behavior a reviewer actually wants isn't a
cleverer scraper that always returns a number — it's a system that (a) tries
harder within bounded, auditable limits, and (b) when it still can't be sure,
says exactly what's missing ("the form didn't specify which club") and shows a
labelled example rather than fabricating "the" price. Chasing "always get a
number" would have pushed us straight into the fabrication failure the brief
calls an automatic fail; naming the missing input is both smarter *and* safer.
Also: keyword link-ranking silently drops good pages — the LLM ranker must see
the *unfiltered* same-site link set, not the keyword-filtered one.

### 2026-07-15 — A `pdf_mode`-only cover page must actively suppress its web-only twin, not just add on top of it

When we added the PDF cover page (Phase 5.5) we treated it as pure addition —
insert a new section, leave everything downstream untouched. But the
Overview panel's header/glance-card/warning-boxes/attention-list existed
*for the interactive web view*, where there's no cover page and Overview is
the first screen a reviewer sees. Once a cover page exists, that same
content becomes a duplicate in the PDF's linear document, not a second
useful screen — since a PDF has no tabs, everything renders back-to-back. A
new pdf_mode-only section always needs a paired audit of what it's now
making redundant elsewhere in the same unrolled document; "add a cover page"
and "make the following content pdf_mode-conditional" are the same change,
not two.

### 2026-07-15 — A URL fragment/anchor is not a different page, but a naive link-dedup check will treat it as one
**What happened:** building the bounded subpage-rescue feature, the first
live test against Sample 10 showed it burning one of its two allowed
follow-up fetches on `https://graciebarra.com/#modal-bookclass` — a
same-page anchor that opens a "book a class" modal via JavaScript, not a
different document at all. `find_candidate_subpages()`'s original dedup
logic compared full URL strings (`link.rstrip("/")`), so a fragment-only
variant of the homepage looked like a brand-new, unvisited URL and passed
straight through. Fetching it just re-downloaded the exact same homepage
content already checked, for zero benefit, while eating into the tightly
bounded "at most 2 follow-ups" budget the whole point of this feature was
built around. **What we changed:** added `_page_identity()`, which strips
the fragment and query string before comparing a candidate against the
already-fetched URL, so `#anything` and `?anything` variants of a page
already checked are correctly recognized as the same page and excluded.
**What to avoid next time:** any "have I already seen this URL" check needs
to decide up front whether identity should be exact-string or
same-document — for anything that's actually going to be *fetched* (as
opposed to, say, displayed as a distinct link to a user), same-document
identity (path only, ignoring fragment/query) is almost always the correct
comparison, since a fragment never changes what a plain HTTP GET returns.
This was caught by an actual live run against a real site with a real modal
trigger, not by unit tests with synthetic URLs — a reminder that link
discovery/crawling logic in particular benefits from at least one real
non-mocked test pass before considering it done.

### 2026-07-15 — `loading="lazy"` is invisible in a normal browser tab and silently breaks a headless print/PDF render
**What happened:** two evidence images came out as blank gray boxes in the
exported PDF, even though calling the exact same capture function directly
and reading the resulting bytes proved the image was fine. The gap was
entirely in *how the PDF is produced*: `write_report_pdf` renders the full
`report.html` template in `pdf_mode` (every tab unrolled into one long
linear document, since a PDF has no clickable tabs) and calls `page.pdf()`
after `page.wait_for_load_state("networkidle")`. `loading="lazy"` on an
`<img>` defers the browser from ever issuing that image's network request
until it nears the viewport — and in a single long unrolled document, most
evidence images sit far below the default viewport height, so their request
never fires at all, and `networkidle` (which only tracks *in-flight*
requests) is satisfied without them. The interactive web view never showed
this because a human scrolls, which is exactly what triggers a lazy image's
load. **What we changed:** `loading="lazy"` is now emitted conditionally —
`{% if not pdf_mode %}` — everywhere it appears in `report.html`, so the
PDF-mode render eager-loads every image up front. **What to avoid next
time:** any attribute that depends on viewport/scroll behavior (lazy-load,
`IntersectionObserver`-based reveal, virtualized lists) needs a second look
whenever the same template is also rendered headless/off-screen for a
non-interactive artifact (PDF, static export, thumbnail) — it can pass every
manual click-through test in a real browser and still silently fail in the
one context where a human never scrolls it into view.

### 2026-07-15 — Attaching "generic context" evidence to every finding by default quietly produces contradictions once a targeted crop sometimes fails
**What happened:** every finding was given the shared whole-page screenshot
*plus* a second, per-criterion capture attempt; when that attempt failed to
literally locate the LLM's quote as a DOM element (common — the quote is
often a close paraphrase, not verbatim source text), the fallback silently
manufactured a second whole-page image labeled "Context reviewed — no public
X clearly visible on the page." For a finding whose status was "Found," that
caption sat directly underneath a genuinely correct quote and a "Found"
badge, flatly contradicting them, and doubled the embedded-image count for
most findings, which in turn worsened PDF page-break behavior (large
`break-inside: avoid-page` blocks got pushed to the next page more often,
producing bigger blank gaps). **What we changed:** `capture_targeted()` now
returns `None` instead of a fabricated fallback when it can't produce a real
crop; the caller attaches exactly one evidence image per finding — the real
crop if one exists, otherwise the single already-captured whole-page
evidence object, never both. **What to avoid next time:** a "helpful"
unconditional default (attach context evidence to everything, just in case)
can look harmless in isolation but compounds badly the moment a secondary,
best-effort step (a literal-text DOM locate) has a non-trivial failure rate
— audit what the fallback path actually produces, not just the happy path,
especially where it's paired with other status/caption text a reviewer will
read side by side.

### 2026-07-15 — A "targeted" evidence screenshot can be geometrically correct and still show the wrong thing, because a screenshot captures composited pixels, not the DOM element in isolation
**What happened:** the user's manual QA on Sample 10 (graciebarra.com) found
that 3 of 4 targeted evidence crops showed a cookie-consent banner instead of
the quoted proof text, even though the report's *text* correctly quoted the
real page content. Investigation (via a dedicated Explore-agent code read,
not a guess) confirmed `screenshot_element_by_text()` in
`research/playwright_client.py` was doing everything right at the DOM level
— `page.get_by_text(needle).first` genuinely found the correct element and
`scroll_into_view_if_needed` genuinely scrolled to it. The bug was one level
below that: `locator.screenshot()` renders whatever is *visually painted* at
that element's screen coordinates at capture time, and a fixed/sticky-
position cookie banner was still on top of the viewport, with nothing in the
codebase ever having dismissed or hidden it (`grep -rniE "cookie|consent|
dismiss|accept|banner" src/` returned zero matches before the fix). This
explains why three *different*, unrelated criteria all showed the identical
banner artifact — it had nothing to do with which text was targeted; it was
purely "whatever fixed-position element happens to be on top of the viewport
right now," which for a fresh page load is very often the cookie banner.
**What we changed:** added a generic, best-effort
`_suppress_cookie_banners(page)` — try clicking a common "Accept"-style
button by role/name (short 1s timeout, silently continue if none match),
then unconditionally inject CSS that force-hides anything matching common
cookie/consent id/class patterns or known vendor selectors (OneTrust,
Cookiebot, Osano, Quantcast) — called right after every `page.goto()` and
before any screenshot, in both the whole-page Playwright fallback and the
targeted per-criterion crop function. Firecrawl's primary fetch path got the
equivalent fix via its `actions` parameter (`ExecuteJavascriptAction`
injecting the same hide-CSS before Firecrawl's own screenshot/markdown
extraction runs), since Firecrawl is a separate rendering pipeline entirely
and would otherwise still bake the banner into the "official" whole-page
capture and even leak its text into the markdown the LLM evaluates.
**What to avoid next time:** don't assume "the locator/selector found the
right element" is sufficient proof a screenshot is correct — a screenshot is
a photograph of the whole rendered viewport at that moment, not an extraction
of just that element, so *anything else rendered on top* (banners, modals,
toasts, loading overlays) can silently corrupt an otherwise-correct capture.
This class of bug is invisible to route-level/unit tests that only check
"did a request succeed" — it was only caught by the user actually opening
the evidence viewer and looking at the images, reinforcing the project's
established practice (see the PDF flexbox entry below) that visual output
must be visually inspected, not just status-code-checked.

### 2026-07-15 — Chromium's print engine can fragment a flex row mid-element, leaving orphaned children at a page break
**What happened:** building the PDF export, `break-inside: avoid` (later
`avoid-page`) was applied to `.finding-card` and `.finding-card summary`,
expecting it to keep each finding's header row atomic across a page break.
Instead, visually inspecting the actual generated PDF (not just checking
that it opened and had the right page count) showed stray, orphaned `›`
chevron characters floating alone at the bottom of several pages, with the
rest of that same row's content (status badge + question text) correctly
appearing at the top of the next page. Root cause: `summary` is `display:
flex` with the chevron pushed to the far end via `margin-left: auto` — when
Chromium's print pagination decides a flex container doesn't fit, it can
still leave a sliver of an individual flex child rendered on the departing
page before moving the rest to the next one, a known-flaky interaction
between CSS flexbox and paged-media fragmentation. `break-inside`/`
break-after` rules did not fully prevent it.
**What we changed:** rather than fight the fragmentation algorithm, removed
the actual cause — the chevron is a "this is expandable" affordance, and in
PDF mode every card is already forced open (nothing is collapsible in a
static document), so it serves no purpose there. Hid it entirely for
`pdf_mode` (`{% if not pdf_mode %}` around the `.chev` span). Verified fixed
by regenerating and re-reading the actual PDF pages, not just re-running
the route and checking `status == 200`.
**What to avoid:** `break-inside`/`break-after` CSS is necessary but not
sufficient for flexbox content in paged/print contexts in Chromium — when a
print-pagination artifact appears, check whether the offending element is
actually needed in that context before trying to out-CSS a browser engine
quirk. And: a PDF/print bug is a visual bug — it will not surface via
route/status-code tests or file-size checks; it requires actually opening
and looking at the generated pages.

### 2026-07-15 — Dynamically-added form rows need their cross-referencing dropdowns populated on creation, not just on edit
**What happened:** the checklist wizard's "compare a price" and "exclusion
list" question types both have a `<select>` that must list the category's
currently-defined fields (e.g. so a reviewer can pick "which field holds the
item name"). `refreshFieldOptions()` was wired to run whenever a field row
was added/edited/removed — but not when a *new question row* was added.
Route-level tests (`tests/integration/test_manage_checklists_routes.py`)
posted JSON directly and couldn't catch this, since they never execute
JavaScript. Only a real Playwright pass against the running server —
clicking "Add a question," picking "exclusion list," then trying to select
the item field — surfaced it: `select_option()` timed out because the
`<select>` had zero `<option>` elements.
**What we changed:** `addQuestionRow()` now calls `refreshFieldOptions()`
itself immediately after the row is inserted, so a freshly-created row's
selects are populated from whatever fields already exist at that point,
independent of whether any field row is later edited.
**What to avoid:** for any dynamically-created form element that depends on
state defined elsewhere in the same form (cross-referencing dropdowns,
computed defaults, etc.), populate it at creation time — don't rely solely
on the *other* state's change handlers to eventually reach it. And: route/
API-level tests are not a substitute for at least one real browser pass on
any feature with non-trivial client-side JS: they will not catch bugs that
only manifest in DOM/event wiring.

### 2026-07-15 — `exclusion_list` checks were silently gated behind a successful page fetch
**What happened:** while authoring the HRI/OTPS configs (Phase 3), noticed
that `evaluator.py`'s dispatch loop only calls `_dispatch()` (which routes to
`evaluate_exclusion_list`) *after* confirming `fetch_result.accessible` —
meaning if a provider/product link were ever dead or blocked, an
exclusion-list criterion would incorrectly come back "Needs Review — site
inaccessible" even though the exclusion check needs zero page content: it
only compares the form's own `item_name` against the config's exclusion
list. This is exactly the kind of check the brief calls out as
safety-critical (Sample 07's laptop test) — it must never silently
degrade just because a website happened to be down that day.
**What we changed:** the fetch-error branch in `evaluator.py` now
special-cases `check_type == "exclusion_list"` and runs
`evaluate_exclusion_list` directly regardless of fetch outcome, before
falling through to the generic "site inaccessible" path for checks that
actually do need page content.
**What to avoid:** when a `check_type` is added that doesn't actually depend
on the fetched page (i.e., it's a pure form-data rule), don't let it inherit
gating logic written for page-dependent checks just because it shares the
same `verifiable: web` dispatch loop — check what data each check_type
*actually* consumes, not just which bucket it's filed under.

### 2026-07-15 — `flex: 0 0 220px` becomes a **height** constraint once the parent flex-direction flips
**What happened:** the PM's feedback specifically flagged "awkward navigation
around 799px." The sidebar nav's base rule was `nav.tabs { flex: 0 0 220px;
... }`, written assuming a row-direction parent (desktop: sidebar width =
220px). The responsive `@media (max-width: 900px)` block correctly switched
`.layout` to `flex-direction: column` and `nav.tabs` to `flex-direction: row`
internally, but never reset `nav.tabs`'s own `flex: 0 0 220px` — so in the
now-column-direction `.layout`, that same declaration became a **220px height
cap** on the tab strip, squeezing all 5 tabs into a tiny boxed area at the
top-left instead of a full-width horizontal bar. This is exactly what a
Playwright screenshot at 799px showed.
**What we changed:** added `flex: 0 0 auto;` to `nav.tabs` inside the
900px media query, overriding the desktop value.
**What to avoid:** when a responsive breakpoint flips a flex container's
`flex-direction`, explicitly re-check every `flex: 0 0 <fixed-px>` rule on
its children — the same shorthand silently changes axis (width → height or
vice versa) with the parent's direction, and a shrunken box like this is
easy to miss in a full-page screenshot review if you don't scroll/inspect
the actual bounding box.

### 2026-07-15 — A reviewer override note must invalidate the stale LLM-written short summary
**What happened:** after adding a separate `short_note` (LLM-written,
one-line) distinct from the full `note`, overriding a finding's `note` via
the reviewer edit form left the old system-generated `short_note` displayed
in the collapsed card — so a reviewer's actual override text was invisible
until the card was expanded. Caught by the existing Sample 01 E2E test
failing after this change (not a new test — the existing assertion on
collapsed-card text broke, correctly, because the behavior it depended on
had changed).
**What we changed:** `Finding.apply_reviewer_override` now clears
`short_note` (saving the original to `original_short_note` for restore), so
`display_short_note` falls back to a truncation of the *new* note; the E2E
test was updated to expand the card before asserting on the full note, since
that's what the redesigned progressive-disclosure card intentionally does.
**What to avoid:** any time a finding has two note-like fields at different
detail levels, every mutation path (override, restore, regenerate-reapply)
needs to keep both in sync — a derived summary field silently going stale
after an edit is a real correctness bug, not just a cosmetic one.

### 2026-07-15 — Playwright `inner_text()` reflects CSS `text-transform`, not raw HTML
**What happened:** the Sample 01 E2E acceptance test asserted `"Reviewer
decision" in card.inner_text()`, which failed even though the correct text
was genuinely present — because `.overridden-tag` is styled
`text-transform: uppercase`, and Playwright's `inner_text()` returns the
*rendered* text (respecting CSS), not the literal HTML content.
**What we changed:** lowercased both sides of the comparison in the test.
**What to avoid:** when asserting on text content styled with CSS
transforms (uppercase/capitalize/lowercase), compare case-insensitively —
don't assume `inner_text()` matches the HTML source casing.

### 2026-07-15 — `|tojson` inside a double-quoted inline `onclick` HTML attribute breaks parsing
**What happened:** the evidence-viewer lightbox call was wired as
`onclick="openLightbox('...', {{ e.label|tojson }}, ...)"`. `|tojson` wraps
string output in double quotes; embedding that inside an HTML attribute
already delimited by double quotes breaks the attribute at the first
`tojson`-produced `"`, silently corrupting the page's inline `<script>`
parsing (`Unexpected end of input`) with no server-side error — only
visible via a real browser console check. The button existed and looked
fine; clicking it just silently did nothing (`lightbox.open` stayed false).
**What we changed:** replaced inline `onclick="...(...)"` calls with
`data-*` attributes (normal Jinja-escaped template output, not `tojson`) and
a single delegated `document.addEventListener('click', ...)` handler that
reads `dataset.*`. More robust generally — also fixes keyboard activation
(added Enter/Space handling) which inline `onclick` on a `<div>` never had.
**What to avoid:** never combine `|tojson` output with inline HTML event
handler attributes, regardless of quote style chosen — use `data-*`
attributes plus a delegated listener instead. Also: always verify new
interactive JS with a real Playwright click + `page.on('console'/'pageerror')`
check, not just a visual screenshot — a broken onclick handler produces no
visible symptom in a static screenshot.

### 2026-07-15 — Playwright locator ambiguity: nested `<details>/<summary>` and repeated form buttons
**What happened:** two different tests hit `strict mode violation` errors:
(1) `.locator("summary")` inside a finding card matched both the outer
`<details class="finding-card">`'s summary AND the nested
`<details class="edit-disclosure">`'s summary (descendant selector, not
direct-child); (2) `#panel-findings form button[type=submit]` matched 18
buttons (Regenerate + every per-finding Mark-reviewed/Restore/Save button).
**What we changed:** used `> summary` (direct-child combinator) for the
nested-details case, and `page.get_by_role('button', name='Regenerate
report')` (accessible-name lookup) instead of a structural CSS selector for
the ambiguous-buttons case.
**What to avoid:** when a page has repeated component structures (finding
cards each containing their own nested disclosure/forms), prefer
role/accessible-name-based Playwright locators over structural CSS selectors
— they're both more robust to markup changes and immediately surface
whether an interactive element has a proper accessible name.

### 2026-07-15 — Real API keys pasted into `.env.example` instead of `.env`
**What happened:** user added the real OpenAI + Firecrawl keys directly into
`.env.example`, which is the one env file NOT covered by `.gitignore` (it's
explicitly negated with `!.env.example` so it always gets committed as a
template). Caught before any `git add`/`commit` happened, so no secrets ever
entered git history.
**What we changed:** moved the real values into `.env` (gitignored), restored
`.env.example` to placeholder values (`sk-replace-me` / `fc-replace-me`),
verified with `git check-ignore -v .env` and `git status` that `.env` is
invisible to git and `.env.example` has no secrets.
**What to avoid:** never assume a user-provided credential landed in the
right file — always verify by re-reading the file and checking git status
immediately after any credential is added, before doing anything else.

### 2026-07-14 — LLM emitted literal `"null"` string under strict JSON schema
**What happened:** a `quoted_snippet` field typed `["string","null"]` in the
JSON schema was returned by the model as the actual 4-character string
`"null"` in one case, not a JSON null — this rendered as a visible, confusing
`"null"` quote box in the report.
**What we changed:** added `_normalize_snippet()` — treat blank or
literal-"null" strings as `None` before using them anywhere downstream
(evidence capture targeting, template rendering).
**What to avoid:** don't trust that "the schema allows null" means the model
will always emit a real null for genuinely-absent values — normalize
defensively at the boundary where the LLM response is consumed.

### 2026-07-14 — Deterministic exclusion-list gate must not be LLM-based
**What happened:** N/A (caught at design time, not as a bug) — but worth
recording as a deliberate decision under Key Learnings since it's easy to
"simplify" later by just asking an LLM "is this item excluded?".
**What we changed:** implemented `evaluation/exclusion_list.py` as a pure
keyword-token-overlap function with zero LLM involvement, specifically
because Sample 07 (laptop vs. "Computer Hardware" exclusion) is a named test
case in the brief for exactly this kind of guardrail.
**What to avoid:** never let an LLM be the sole gate on an exclusion-list
check — false negatives here (missing an excluded item) are the worst
possible failure mode for this system. Keep it a deterministic, unit-testable
function.
