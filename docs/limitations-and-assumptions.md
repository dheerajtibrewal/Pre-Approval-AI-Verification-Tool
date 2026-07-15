# Limitations, Assumptions, and Production-Readiness Notes

## What this build assumes

- **Synthetic data only.** All sample applications use fictional
  participants. Production use would require PHI-handling controls this
  exercise deliberately doesn't build: field-level redaction before any
  third-party LLM call (or a private/self-hosted model), encryption at rest,
  access control per FI Coordinator/reviewer, and audit logging that meets
  the agency's actual compliance requirements — not just this tool's
  lightweight `log.md`/review-history trail.
- **No persistent database.** `ApplicationRecord` state (extraction,
  evaluation, reviewer overrides) lives in an in-memory dict for the life of
  the server process. Restarting the server loses in-progress (not yet
  exported) reviews. A production build would need Postgres/similar plus a
  real audit-event table.
- **Single-process, single-worker.** The background research thread
  (`threading.Thread`) works for one reviewer at a time in this exercise;
  production would want a real task queue (Celery/RQ/similar) so multiple
  reviewers can run research concurrently without contending for the same
  in-memory store.
- **API keys via `.env` only.** No secrets manager integration. Fine for a
  local/single-operator deployment, not for a shared production environment.

## What the tool deliberately does NOT try to do

- It never approves or denies a request — every report ends with the human
  reviewer's judgment, not the tool's.
- It never guesses on a checklist item it can't verify from the public web —
  those are always marked Internal, not inferred as yes/no.
- It does not integrate with Enterprise Manager, eVero, the participant's
  budget system, or their Life Plan (explicitly out of scope per the brief).
- It does not handle payment or invoicing.

## Known technical limitations

- **Targeted evidence crops** depend on locating the LLM's exact quoted
  snippet in the live-rendered DOM (via Playwright's text locator). Markdown
  formatting differences between what Firecrawl returns as page text and
  what's actually rendered in the DOM mean this sometimes fails; when it
  does, the tool honestly falls back to a full-page capture labeled as such
  — it never fabricates a crop or mislabels a whole-page image as
  "targeted."
- **LLM judgment is not perfectly deterministic.** Two runs against the same
  page can occasionally reach different Needs-Review-vs-Found conclusions on
  genuinely ambiguous language (e.g., a provider whose site frames itself as
  both a therapeutic and a public recreational program). This is treated as
  correct, cautious behavior, not a bug to eliminate — the tool is designed
  to default to Needs Review rather than force confidence it doesn't have.
  Partially mitigated: every judgment call now self-reports a confidence
  level, and a low-confidence found/not_found verdict gets one independent
  re-check, holding the finding at Needs Review if the two calls disagree
  (`evaluator.py::_evaluate_web_criterion`) — this only catches the cases
  where the model itself flagged uncertainty, not every possible case of
  run-to-run drift.
- **The checkbox-answer parser** (`extraction/checkbox_parser.py`) reads a
  specific, fixed form layout (a YES/NO glyph pair immediately following the
  question text). It is not a general-purpose PDF form-field reader and
  would need rework for forms with a different layout convention.
- **Category coverage**: all 7 categories are implemented and all 10 sample
  applications have been run live end-to-end (see `log.md` for the
  per-sample results table). Two categories (HRI, OTPS) share the same
  exclusion-list check mechanism against different, category-specific lists.
- **Research is single-page by default, with a bounded navigator for prices.**
  The evaluator fetches one URL (the form's stated webpage/item link) and
  evaluates all web-verifiable criteria against that one page's content. If a
  fee/price/schedule-type criterion is still Needs Review afterward, a bounded
  navigator (`evaluator.py::_run_pricing_navigator`) tries to find the missing
  fact: it lets the LLM pick the most promising same-site links (falling back
  to deterministic keyword ranking), follows them up to **2 hops deep** and
  **3 pages total**, and re-checks just those criteria against each page it
  opens. The bounds are fixed constants, never model-controlled — this is a
  bounded, auditable helper, not an open-ended browsing agent. It only triggers
  for fee/price/schedule questions and honestly leaves a finding at Needs
  Review if no followed page answers it.
- **Dead form links fall back to the homepage.** If the exact URL on the form
  is unreachable (e.g. a stale `/join` page that now 404s) but the provider's
  main site is fine, the tool backs off to the site root and researches from
  there, recording a visible "how this was researched" note so the reviewer
  knows the exact page they listed wasn't the one checked. It never silently
  substitutes pages.
- **Location- and tier-specific pricing is reported honestly, not guessed.**
  For providers whose price depends on something the form doesn't specify
  (a franchise/club location like Planet Fitness, or one of several membership
  tiers), the tool does **not** present any single price as "the" price. It
  stays Needs Review and, when the site shows one, attaches a clearly-labelled
  *example* price (with its own grounded screenshot) plus a plain-language
  explanation of exactly what the form would need to specify to resolve it
  (`fee_match.py::_no_price_diagnostic`). This is a deliberate anti-fabrication
  stance: an illustrative data point for the reviewer, never a confirmed fact.
- **Reviewer-facing messages are plain language, not plumbing.** Raw fetch
  failures (HTTP status codes, timeouts, anti-bot walls, DNS errors) are
  translated into what happened and what to do
  (`research/error_messages.py`); the raw technical string is kept only as a
  trailing "Technical detail:" for the audit trail.
- **The report includes one LLM-written paragraph.** A short plain-language
  executive summary is generated at the top of the report
  (`report/summary.py`). It is fed only the tool's already-computed findings
  (never raw website text), is instructed to restate them without adding facts
  or making an approve/deny decision, and is strictly optional — if the call
  fails the report falls back to its deterministic templated line. Everything
  else in the report (statuses, evidence, counts) remains fully deterministic.

## Accuracy guardrails added after live QA (Samples 02/04/07/10)

- **A location/tier-specific price is never confirmed as the applicant's
  price.** If a found price belongs to one branch/club/store or one plan tier
  (which the application form has no field to pin down), it is shown only as a
  labelled example ("Example price — not confirmed for this application") and
  the finding stays Needs Review (`fee_match.py`).
- **Silence is never treated as proof.** For negative criteria ("must be NO",
  "not clinical", etc.), a page being silent produces Needs Review, not Found —
  enforced both in the LLM prompt and, deterministically, by requiring every
  website "Found" to carry a readable targeted-evidence crop of the actual
  proof; if no such crop can be produced, the finding is downgraded to Needs
  Review (`llm_judge.py`, `evaluator.py`). Deterministic exclusion-list checks
  carry their own rule provenance and are exempt.
- **Blocked/anti-bot pages are reported as blocked, not read.** A CAPTCHA /
  "continue shopping" / access-denied shell is detected
  (`research/blocked_detection.py`); the tool reports "the provider blocked
  automated access" and does not run the LLM over the shell or imply the real
  page was reviewed.
- **Appeals reuse the base category's web criteria verbatim.** The loader
  replaces an appeal's web criteria with the base category's at load time
  (`loader.py::_apply_appeal_reuse`), so an appeal can never drift from the
  checks it is meant to re-run. Note: this locks the *criteria*; run-to-run LLM
  verdict drift on genuinely ambiguous pages is still possible and is mitigated
  (not eliminated) by the confidence re-check and the guardrails above.
- **Scanned/rotated/low-text PDFs degrade safely, not silently.** There is no
  OCR pipeline (out of scope). When a PDF has no usable text layer, every field
  is flagged low-confidence for reviewer confirmation with a clear warning —
  nothing is passed through as a clean reading.

## What production-readiness would add

1. A real datastore + task queue (see above).
2. Field-level PHI redaction/tokenization before any external API call.
3. Role-based access control and a real authentication layer for reviewers.
4. Structured, queryable audit logging (not just in-memory review history).
5. Monitoring/alerting on fetch failure rates, LLM error rates, and cost.
6. Multi-page research support per category config.
7. A scheduled re-verification workflow (Brief's "approvals may be
   spot-checked periodically" note) — re-running research on a cadence and
   diffing against the original evidence.
