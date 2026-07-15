# Pre-Approval Website-Verification Tool

Somewhere in a New York disability-services agency, a reviewer opens a PDF, copies a URL out of
it, opens a new browser tab, and starts hunting for a class schedule or a membership fee — so
they can screenshot it, paste it into a folder, and do the same thing again for the next
application. That's the actual job this tool replaces: not the *decision* (a human always makes
that), but the tedious, error-prone, forty-tabs-open research and evidence-gathering that comes
before it.

Give it a completed OPWDD Self-Direction pre-approval application (a PDF) and it will: read the
request, work out which of the seven approval categories it belongs to, go visit the provider's
real public website, capture dated proof of what it found, and hand a reviewer a clean report —
confirmed, not confirmed, or "here's what I couldn't tell, and why." It never says yes or no.
That line is deliberate, load-bearing, and repeated throughout this README because it is the
single most important design constraint in the whole system.

**If you read nothing else, read this:** `log.md` is this project's running engineering diary —
every phase, every bug found, every design decision and the reasoning behind it, in chronological
order. This README is the map; `log.md` is the terrain.

---

## Who should read what

- **A reviewer who just wants to try it** → [Quickstart](#quickstart), then
  [The reviewer journey](#the-reviewer-journey).
- **Someone deciding whether to trust this tool's judgment** → [How it thinks](#how-it-thinks-the-pipeline),
  [Why these models and tools](#why-these-models-and-tools), and
  [Evidence: the load-bearing idea](#evidence-the-load-bearing-idea).
- **A non-technical program lead adding a new category of application** →
  [Adding a new form/checklist](#adding-a-new-formchecklist).
- **An engineer inheriting this repo** → the [Architecture](#architecture) map, `log.md` in full,
  and [Where this goes next](#where-this-goes-next-a-production-roadmap).

## Quickstart

```bash
# 1. Install dependencies (uv manages the Python env; see pyproject.toml)
uv sync
uv run playwright install chromium

# 2. Add your API keys
cp .env.example .env
# edit .env: OPENAI_API_KEY=..., FIRECRAWL_API_KEY=...

# 3. Run the reviewer web app
uv run uvicorn preapproval_tool.web.app:app --reload
# open http://127.0.0.1:8000, upload a PDF from samples/

# — or — run one sample non-interactively and write a committed report package:
uv run python scripts/run_sample.py \
  "samples/Sample-01---Community-Class-GallopNYC.pdf" \
  "output/samples/sample-01-gallopnyc" --category community-classes
```

No API keys are required to explore the *committed* sample output — open
`output/samples/sample-01-gallopnyc/report.html` directly in a browser, or open any of the
committed `report.pdf` files, no server needed.

## Final sample runs

Four samples were run end-to-end against the live pipeline (real OpenAI calls,
real provider websites, real evidence capture) and are committed as **complete,
self-contained audit packages**. Each folder holds `report.pdf`, `report.html`
(opens with no server — evidence images load via relative paths), `report.json`
(structured findings), `evidence-manifest.json`, `run-metadata.json`, and an
`evidence/` folder of date/URL-watermarked captures. These four span four of the
seven categories and both easy and hard evidence conditions.

Each row links the print-ready **PDF** and the structured **JSON**; the full
package folder (with `report.html`, `evidence/`, and the manifests for offline
viewing) sits next to them under `output/samples/`.

| Sample | Category | What it demonstrates | Result | One honest Needs-Review outcome | Report |
|---|---|---|---|---|---|
| **01 — GallopNYC** | Community Class | Clean baseline: a provider that publishes pricing and program detail | 4 Confirmed · 4 Needs Review · 12 internal | The class *schedule* isn't published on the page, so "is there a published schedule?" stays Needs Review rather than being guessed | [PDF](output/samples/sample-01-gallopnyc/report.pdf) · [JSON](output/samples/sample-01-gallopnyc/report.json) |
| **04 — Planet Fitness** | Membership | Franchise pricing that varies by club location the form never specifies | 0 Confirmed · 3 Needs Review · 5 internal | The $15 fee can't be matched to a single published price — it depends on a specific club, so it's held Needs Review with a plain-language explanation, never confirmed off a branch price | [PDF](output/samples/sample-04-planet-fitness/report.pdf) · [JSON](output/samples/sample-04-planet-fitness/report.json) |
| **08 — Weighted Blanket** | OTPS | Amazon product page + OTPS exclusion-list check under an anti-bot wall | 1 Confirmed · 1 Needs Review · 8 internal | Amazon blocked automated access, so "does the page show the item with a visible price?" is honestly reported as blocked → Needs Review (manual check), not read off a challenge screen | [PDF](output/samples/sample-08-weighted-blanket/report.pdf) · [JSON](output/samples/sample-08-weighted-blanket/report.json) |
| **09 — LaGuardia ACE** | Transition Program | College continuing-ed program; provider *is* the requested item | 0 Confirmed · 4 Needs Review · 6 internal | The continuing-ed landing page lists no specific course fee, so "does the program have published fees?" is Needs Review even though the form's $300 is within the $350 cap | [PDF](output/samples/sample-09-laguardia-ace/report.pdf) · [JSON](output/samples/sample-09-laguardia-ace/report.json) |

Every "Confirmed" in these packages is backed by a real capture on disk (the
export validator re-checks this — `validation_issues` is empty in all four
`report.json` files). The remaining categories (Samples 02, 03, 05, 06, 07, 10)
also have committed runs under `output/samples/` as `report.html` + `evidence/`;
those are lighter artifacts (no PDF/JSON bundle) kept to show every category was
exercised.

## The reviewer journey

1. **Upload** a completed application PDF.
2. **Confirm extraction** — every field the tool read is editable before research starts;
   low-confidence fields and the detected category (also correctable) are flagged. Nothing is
   sent to any website yet — this is the tool's version of "asking for clarification" before it
   goes and does something that costs time and money.
3. **Research, in the open** — a real, backend-driven progress screen (not a fake timer) narrates
   the actual pipeline stage: validating the URL, reading the site, capturing evidence, checking
   each criterion, and — when it happens — backing off to the homepage if the form's link is dead,
   or following links to a pricing page the form's own link didn't cover. Every failure is plain
   language, never a raw stack trace or an HTTP status code.
4. **A one-page verdict, then the detail** — the exported PDF opens on a cover sheet: participant,
   provider, item, category, the confirmed/needs-review counts, and a short plain-language summary,
   so a reviewer knows the shape of the case before reading a single finding. Everything below that
   is organized into five sections:
   - **Overview** — the request at a glance, a plain-language fee comparison, and "how to read
     this report."
   - **Findings** — one card per website-verifiable criterion, collapsed by default, with status
     filters and search. Expanding a card shows the applicant's own form answer next to the
     website's verdict, the supporting quote, and the evidence that backs it.
   - **Evidence** — every capture in one place: full-page and targeted screenshots, each with its
     source URL, page title, capture timestamp, and which finding(s) it supports. Click to open a
     zoomable, downloadable viewer.
   - **Internal Checks** — criteria that can't be checked from a website at all (budget approval,
     Life Plan fit, duplication of services...), grouped, each with a specific reason why — never
     generic boilerplate.
   - **Review & Export** — completion status and downloads: a print-ready **PDF** (the
     recommended format — one self-contained document, cover page, evidence images embedded, no
     browser or extra tooling needed to open it), the HTML/JSON forms for anyone who wants them,
     or the complete audit package (.zip: PDF + HTML + JSON + every evidence file + reviewer
     overrides + manifest).
5. **Reviewer actions** — override a finding's status, add a note, or mark it reviewed. The
   system's original result is always preserved alongside the reviewer's decision (never
   overwritten), survives a page refresh, and survives "Regenerate report" (which re-runs the live
   website research from scratch).

## How it thinks: the pipeline

This is the part worth understanding even if you never open the code, because it's the answer to
the question that actually matters: *when should you trust what this tool tells you?*

```
 PDF in                                                                     Report out
   │                                                                             ▲
   ▼                                                                             │
Extract  →  Categorize  →  Load checklist  →  Research  →  Evaluate  →  Assemble report
(pdfplumber   (template        (config/           (Firecrawl →           (deterministic +
 + LLM,        match, LLM       checklists/         Playwright,           grounded LLM,
 schema-       fallback         *.yaml —            SSRF-guarded,         confidence-
 validated)    only if          this file IS         evidence               gated
               ambiguous)       the "checklist"       captured)            self-check)
```

The design choice underneath every box above: **the LLM is a bounded tool inside a fixed
pipeline, never the thing deciding whether evidence exists or what "found" means.** A screenshot
either exists on disk or it doesn't; a quote either appears in the captured page text or it
doesn't. Those checks are plain Python, not a prompt, and they run on every single finding before
it's allowed to say "Confirmed" — see [Evidence: the load-bearing idea](#evidence-the-load-bearing-idea)
below for why that specific design choice exists.

Walking the pipeline stage by stage:

1. **Extract** (`extraction/`) — `pdfplumber` pulls the PDF's actual text layer (deterministic,
   not AI), then a schema-validated LLM call structures it into fields: participant, provider,
   the requested item, the link to check, the stated fee. A separate regex-based parser
   (`checkbox_parser.py`) reads which YES/NO box the *applicant* actually checked on the form,
   independent of the LLM, so the report can show "applicant said X, website shows Y" side by
   side.
2. **Categorize** (`categorization/`) — matches the form against each checklist's declared
   `form_template_signature` first (deterministic, and correct on all 10 samples in this repo's
   own testing); only falls back to an LLM guess if nothing matches, and always surfaces the
   result for the reviewer to correct before research starts.
3. **Load the checklist** (`checklist_engine/`) — reads the matched category's
   `config/checklists/*.yaml`. This one file *is* the checklist: which questions apply, which of
   them a website can actually answer, which caps/exclusion lists apply, and how each one should
   be checked. Nothing about a category is hard-coded in Python — see
   [Adding a new form/checklist](#adding-a-new-formchecklist).
4. **Research** (`research/`) — fetches the provider's page through a two-tier strategy
   (Firecrawl first, a local headless browser as fallback — see
   [Why these models and tools](#why-these-models-and-tools)), but only after the URL passes an
   SSRF guard that blocks private/loopback/metadata addresses and non-http(s) schemes. If the
   form's exact link is dead, it backs off to the site homepage and notes it did. If a
   fee/price/schedule question is still unanswered after the main page, a bounded navigator lets
   the LLM pick the most promising same-site links and follows them up to two hops deep — see
   [Made it smarter](#made-it-smarter-what-changed-and-why) below.
5. **Capture evidence** (`evidence/`) — every claim gets a real, date-and-URL-watermarked
   screenshot before it's allowed to matter. This is the stage that makes the next one honest.
6. **Evaluate** (`evaluation/`) — each criterion runs through whichever check its config declares:
   a deterministic rule, a deterministic exclusion-list/fee-cap comparison, or a grounded LLM
   judgment call that must cite an exact quote from the page it actually saw. A quote that can't
   be found in the real captured text is thrown out and the finding is held at Needs Review — no
   exceptions, checked in code, not just asked of the model nicely.
7. **Assemble the report** (`report/`) — turns the structured findings into the reviewer's report:
   the cover page, a grounded plain-language summary (generated only from the computed findings,
   never from raw web text), the five-tab workspace, and the PDF/HTML/JSON/zip exports.
8. **Human review** — every screen, every finding, every export ends with the same sentence:
   *this report assists a human reviewer and does not itself approve or deny this request.*

## Why these models and tools

Every external dependency in this project was picked for a specific job, not by default. Here's
the reasoning:

- **OpenAI GPT-4o** (in-product model, `.env`'s `OPENAI_MODEL`) — the model actually reasoning
  about whether a page's text supports a criterion. Chosen for strong instruction-following on a
  structured-output schema (every single call is JSON-schema-validated before the result is
  trusted anywhere downstream) and for being fast/cheap enough to run several judgment calls per
  application without the tool feeling slow. It does a few other bounded, schema-constrained jobs
  too — structuring the extracted PDF fields, ranking which links the pricing navigator should
  follow, and writing the report's plain-language summary from the already-computed findings — but
  it is never the thing deciding *whether* a screenshot was taken, only *what a screenshot means*,
  and never the thing that sets a status or invents a fact — see the pipeline and
  [Evidence](#evidence-the-load-bearing-idea) sections.
- **Firecrawl** (primary fetch/render) — most provider sites in this domain are ordinary small-
  business sites, but a few (Amazon product listings, anything behind Cloudflare) actively push
  back against a plain headless browser hitting them from a script. Firecrawl handles JS
  rendering, anti-bot evasion, and returns clean text *and* a full-page screenshot in one call —
  solving the single biggest reliability risk in this project (a fetch that silently comes back
  empty or blocked) without hand-rolling proxy/retry logic. It's also what makes the follow-up
  subpage fetch cheap: link discovery (below) reuses the same links Firecrawl already extracted.
- **Playwright (Chromium)** — the fallback when Firecrawl fails, and the only way to take a
  *targeted* screenshot (Firecrawl doesn't expose DOM element coordinates, only full-page
  captures). Also does the actual PDF rendering for the exported report — since a browser was
  already a hard dependency for research, `page.pdf()` meant no second PDF-generation library.
- **pdfplumber** — plain, deterministic PDF text extraction. Not AI, and deliberately not: the
  raw text layer of the *application form itself* is exactly the kind of structured, well-behaved
  input that doesn't need a model to read reliably, and using a model for it would just be an
  extra point of failure and cost for no benefit.
- **Claude Code (Sonnet 5)** — not part of the product at all; this is the agent this entire
  project was *built with* (planning, every line of code, every test, every live debugging
  session). See `AI-CONVERSATION.md` for the real, exported build conversation — a different role
  from GPT-4o, and worth keeping distinct: one wrote the tool, the other is what the tool calls at
  runtime.

## Evidence: the load-bearing idea

If you take away one engineering decision from this whole project, make it this one:

> **A finding can never be "Confirmed" without a real, on-disk evidence capture.** This is
> enforced in code (`Finding.__post_init__` in `evaluation/models.py`) — not a prompt asking the
> model to behave, a hard invariant that runs on every single finding, every time, including when
> a previously-reviewed finding is reconstructed from a saved override. If a "found" verdict
> somehow arrives with no evidence attached, it is automatically downgraded to Needs Review before
> a reviewer ever sees it.

Two supporting rules make that invariant meaningful rather than just decorative:

- **A quote must be real.** The LLM's judgment call must cite an exact excerpt from the page it
  was shown. Before that quote is trusted as "grounding" for anything, `is_quote_grounded()`
  independently checks that the excerpt actually appears in the real captured page text — an
  LLM claiming a quote that was never really there gets its finding discarded and held at Needs
  Review, not silently trusted.
- **A screenshot must be honest about what it shows.** A "targeted" crop is only ever labeled
  that way if a real, distinct crop was actually produced; when the crop attempt fails, the tool
  falls back to the shared whole-page capture rather than mislabeling a generic screenshot as
  pinpoint proof.

Every evidence image also carries a visible, burned-in date/time + URL watermark, because an
audit needs to prove what a site showed *on that date* even if a copy of the file loses its
metadata later.

## Made it smarter: what changed, and why

Several things were added specifically to catch mistakes this tool could otherwise make quietly,
or to behave the way a sharp human researcher would. Every one is **bounded** on purpose — the
goal was making individual applications more reliable and more honest, not turning the tool into
an open-ended web-browsing agent that loops up cost and latency:

- **Confidence-gated self-consistency checking.** Every LLM judgment call now also reports its
  own confidence (high/medium/low) — not performative, an honest signal. When a call comes back
  low-confidence on a `found`/`not_found` verdict, the tool spends exactly one more independent
  call re-asking the same question. If the two calls agree, the result stands, now double-
  checked. If they disagree, that disagreement *is* the finding — the tool holds it at Needs
  Review with a note explaining that its own two attempts didn't match, rather than picking one
  arbitrarily. This exists because ambiguous provider pages really do produce different verdicts
  across separate runs (observed directly during this project's own QA), and a reviewer deserves
  to know when a "confirmed" is a coin-flip versus a slam dunk.
- **A bounded pricing navigator.** Prices often aren't on the page the form links to — they're a
  couple of clicks away (a national gym chain's price lives on a specific club's "offers" page;
  a museum's membership fee is behind a "Become a Member" link the homepage only mentions in
  passing). When a fee/price/schedule question is still unanswered, the navigator lets the LLM
  pick the most promising same-site links (falling back to deterministic keyword ranking),
  follows them **up to two hops deep and three pages total**, and re-checks *only* the still-
  unresolved criteria on each page it opens. The limits are fixed constants in code, never
  model-controlled — this is a bounded, auditable helper, not an agent that decides for itself
  how long to keep browsing. Letting the model rank links (not just keywords) is what lets it
  recognize a good page like `/become-a-member` that a fixed keyword list would silently drop.
- **Dead-link recovery.** If the exact URL on the application form is unreachable (a stale `/join`
  page that now returns "not found") but the provider's main site is fine, the tool backs off to
  the homepage, researches from there, and records a visible "how this was researched" note so
  the reviewer knows the exact page they listed wasn't the one checked. It never silently swaps
  one page for another.
- **Honest about prices it can't pin down — and *why*.** For providers whose price genuinely
  depends on something the form doesn't specify (which club location, which membership tier), the
  tool does **not** present any single price as "the" price. It stays Needs Review and explains
  exactly what the form left unspecified ("this provider's price depends on a specific club
  location, which the form doesn't specify"), and — when the site shows one — attaches a clearly-
  labelled *example* price with its own grounded screenshot ("as a reference point... this is
  illustrative, not necessarily the price that applies"). This is the anti-fabrication rule
  applied to its hardest case: the smart move isn't to guess a number, it's to tell the reviewer
  precisely what's missing and show a concrete example without ever dressing it up as the answer.

All of these are covered by fixture-based tests (`tests/unit/test_evaluator_smart_features.py`
including the two-hop navigation and dead-link-recovery cases, `tests/unit/test_link_discovery.py`,
`tests/unit/test_link_ranker.py`, `tests/unit/test_fee_match_diagnostic.py`) that mock every
external call, so they run in under a second and never touch a real API.

## Report formatting

The report is the actual product — a non-technical reviewer has to be able to act on it
immediately — so it went through repeated polish passes, each verified by actually generating a
PDF and reading every page (not just checking that a file appeared):

- **A plain-language summary at the top.** A short executive summary opens the report ("Planet
  Fitness is confirmed as open to the public. The tool could not confirm the exact membership
  price because prices differ by club location, which the form doesn't specify..."). This is the
  one place LLM-written prose appears in the report body, and it's deliberately fenced in: it's
  fed *only* the tool's already-computed findings (never the raw website text), told to restate
  them without adding a fact or making an approve/deny call, and is strictly optional — if the
  call fails the report simply falls back to a deterministic templated line. Everything else in
  the report (statuses, counts, evidence) stays fully deterministic.
- **Plain-language messages, never raw plumbing.** A reviewer used to see "Firecrawl reported HTTP
  404 for https://..."; now they see "The exact web address on the application form doesn't exist
  anymore — the page returned 'not found'... a reviewer should check the provider's current
  website." Timeouts, anti-bot blocks, and DNS failures each get their own plain explanation. The
  raw technical string is kept only as a trailing "Technical detail:" for the audit trail — the
  lead sentence explains what happened and what to do.
- **A one-page cover sheet** up front — participant, provider, category, the source website, the
  submitted fee, big verdict counts, the appeal's original denial reason if this is an appeal, and
  the summary — so a reviewer opening the PDF cold sees the whole shape of the case before
  scrolling through eight-plus individual findings. The cover is deliberately compact so it
  reliably fits a single page, and the "what needs your attention" list leads the first content
  page rather than stranding itself on a near-empty second cover page.
- **Denser print-mode spacing.** The interactive web view's generous whitespace is right for a
  screen; the printed audit document uses tighter card padding and image sizing so more genuinely
  useful content fits per page without feeling cramped.
- **No more forced blank pages.** Every report section used to force its own fresh page in the
  PDF, which meant a short section (a handful of evidence thumbnails, a brief completion-status
  card) could burn most of a page on nothing. Now only the Findings section — the one that's
  genuinely long — gets a hard page break; everything after it flows continuously, and reference
  cards (like the status legend) are allowed to flow across a page boundary instead of jumping
  whole onto an otherwise-blank page.

## Adding a new form/checklist

**Option A — no YAML, no code (recommended for non-technical users):** open `/manage-checklists`
in the running app. A plain-language wizard walks through identifying the form, listing the fields
to extract, and describing each checklist question ("Can this be checked from the website?" /
price caps / exclusion lists / "why can't this be checked" for internal items) — the
`check_type`/`verifiable` vocabulary below is never shown to the user.

The full workflow, from a blank category to a live one:

1. **Start editing** — from `/manage-checklists`, click **Add a new category** (blank wizard),
   or **Edit** next to an existing live category (which clones it into a fresh draft so you never
   edit a live config directly).
2. **Fill in the wizard and Save.** Saving *always* creates or updates a **draft** — by design, a
   saved wizard never touches live reviewer traffic. Drafts are listed on the Manage Checklists
   page so you can come back to an unfinished one later.
3. **Open the draft's review page.** It automatically **validates** the draft and lists any
   problems in plain language. While there are validation errors, the Test and Publish buttons
   stay disabled.
4. **(Recommended) Run a test.** From the review page you can run the draft against a real sample
   PDF and see exactly what it would produce — before it affects anything real.
5. **Publish.** Clicking **Publish** re-validates the draft, checks the category name isn't
   already taken, writes the category's `config/checklists/<category_id>.yaml`, clears the
   checklist cache so it's **live immediately for new applications** (no server restart), and
   deletes the draft. If you renamed a category while editing, the old YAML is removed too.

There is no separate deploy step — Publish *is* the go-live, gated only by validation passing.
Because publishing writes a real file into `config/checklists/`, that change is on disk in the
repo; to keep it under version control (and to have a restore point) you'd commit the new YAML
yourself — the app doesn't touch git. Drafts are saved to disk under `data/checklist_drafts/`, so
an unpublished draft survives a server restart until you publish or discard it.

**Undoing an edit.** Before you publish, editing a live category only ever changes a *draft* — the
live checklist is untouched, so discarding the draft (or just not publishing) keeps the previous
list exactly as it was. After you publish, though, there is **no in-app rollback**: publishing
overwrites the category's YAML and keeps no backup. To get a previous version back you'd restore
the committed YAML from git (`git restore config/checklists/<id>.yaml`) or re-enter the old values
in a new draft and publish again — which is precisely why the config files are worth committing,
and why production would add versioning + a **review-gated** publish step (see
[the roadmap](#where-this-goes-next-a-production-roadmap)) so going live is an approved, reversible
action rather than something any single user can do unilaterally.

**Option B — hand-author the YAML directly:**

1. Copy `config/checklists/community-classes.yaml` as a starting point.
2. Fill in `category_id`, `display_name`, `form_template_signature` (strings that uniquely
   identify this form in its PDF text), `fields` (header fields to extract), and `criteria` (each
   tagged `verifiable: web | internal | document`, and a `check_type`: `rule`, `llm_judgment`,
   `fee_match`, or `exclusion_list`).
3. For internal criteria, set `explanation` (what record would actually answer it) and `group`
   (for the Internal Checks tab).
4. Set `form_question` on any criterion whose displayed `question` text has been reworded from the
   literal PDF wording (e.g. a "(must be NO)" suffix added for clarity) — this is what the
   checkbox-answer parser matches against.
5. For a `fee_match` criterion, `caps: { tolerance_pct: N }` checks the published price against
   the form-stated fee within a percentage tolerance (Community Classes/Memberships-style);
   `caps: { max: N }` instead checks the published (or form-stated, as a fallback) price against a
   fixed dollar ceiling (Coaching/Transition Program-style caps).
6. No code changes needed — the engine reads the YAML; add a fixture PDF under `tests/schema/` if
   you want the loader test to cover it.

## Architecture

```
config/checklists/*.yaml     One file per form category — see "Adding a checklist" above.
                              All 7 categories in the brief are implemented.

src/preapproval_tool/
  extraction/       PDF text (pdfplumber) + LLM field extraction (OpenAI,
                     JSON-schema validated) + checkbox-answer parsing (reads
                     the applicant's own YES/NO answers off the form).
  categorization/    Deterministic template-signature match; LLM fallback
                     only if ambiguous — never guesses silently.
  checklist_engine/  Loads + validates config/checklists/*.yaml; the
                     non-technical draft/wizard/publish workflow behind
                     /manage-checklists.
  research/          fetch_page(): Firecrawl (primary) -> Playwright
                     (fallback), always through the SSRF guard first.
                     link_discovery.py (same-site candidate links, site
                     root, URL identity) + link_ranker.py (LLM link
                     ranking) power the bounded pricing navigator;
                     error_messages.py turns raw fetch failures into
                     plain language.
  security/          SSRF guard (url_guard.py) — blocks private/loopback/
                     link-local/metadata IPs and non-http(s) schemes.
  evidence/          Screenshot capture, date/time+URL watermarking,
                     cookie-banner suppression, content-hash dedup.
  evaluation/        evaluator.py orchestrates (including the bounded
                     2-hop pricing navigator + dead-link recovery);
                     llm_judge.py (grounded LLM judgment + confidence,
                     quote must be verified against the actual captured
                     page text or the finding is held at Needs Review);
                     fee_match.py (incl. the "what's missing from the
                     form" price diagnostic); exclusion_list.py
                     (deterministic, no LLM); rule.py (internal/document
                     criteria).
  report/            Builds the report data model, generates the grounded
                     plain-language summary (summary.py), renders
                     report.html (cover page + 5-tab workspace), the PDF
                     via Playwright.
  web/               FastAPI app (upload -> confirm -> progress -> report),
                     export.py (package validation + zip building).

scripts/run_sample.py   Non-interactive batch runner — PDF in, committed
                        report package out. Used to produce output/samples/*.
```

## Security

- **SSRF guard**: every provider URL is validated before any fetch — blocks non-http(s) schemes,
  localhost, and private/loopback/link-local/cloud-metadata IP ranges (tested in
  `tests/security/test_url_guard.py`). Every page the pricing navigator follows (and the homepage
  it backs off to when a form link is dead) goes through `fetch_page`, and therefore the exact
  same guard — there is no separate fetch path that could bypass it. Link-following is also
  constrained to the provider's own site.
- **Prompt injection**: all page/document content is passed to the LLM as clearly delimited
  untrusted data with an explicit "ignore embedded instructions" system prompt; the model's
  output is schema-validated before use — it can never set a status or evidence path directly.
- **Upload validation**: PDF magic-byte check, 20MB size limit, corrupted PDFs fail cleanly (400,
  not a 500 traceback) — see `tests/security/test_upload_validation.py`.
- **No secrets in code/logs/exports**: keys only via `.env` (gitignored); `export.py::validate_export`
  scans report content for key-shaped strings before allowing a package download.
- **Evidence-integrity validation**: re-checked at export time, independent of the
  construction-time invariants — every referenced evidence file must actually exist on disk.

## Accessibility & responsiveness

- Full keyboard navigation: tabs are a proper ARIA `tablist`/`tab`/`tabpanel` with arrow-key
  switching; the evidence viewer is a native `<dialog>` (built-in focus trap + Escape-to-close +
  inert background). `:focus-visible` outlines throughout; `prefers-reduced-motion` respected.
- Status is never color-only — every status badge carries a text label.
- Verified with real Playwright passes at 390px, 768px, and 1280px: no horizontal overflow; the
  sidebar becomes a horizontal scrollable tab bar on narrow screens.

## Runtime cost and usage

Per application, end to end. **Bounds** are hard constants read from the code
(not estimates); **observed** figures are from the four committed live runs;
anything labelled *estimate* is a rough figure and is called out as such. No
dollar figures are quoted here because they depend entirely on current OpenAI /
Firecrawl list pricing — multiply the call counts below by whatever the current
per-call/per-token rate is.

| Resource | Per run | Source |
|---|---|---|
| **OpenAI calls** (model: `gpt-4o`, overridable via `OPENAI_MODEL`) | ~6–12: 1 field extraction, 0–1 category-classification fallback (only when the deterministic template match is inconclusive), 1 grounded judgment per web-verifiable criterion (~3–8 depending on category), 0–2 navigator link-ranking calls, 1 executive-summary paragraph | Call sites are fixed in code; criterion count comes from each category's checklist config |
| **Schema-repair retries** | ≤1 per LLM call (one validation-error re-prompt, then it raises) | `llm/client.py` `max_repair_attempts=1` (bound) |
| **Firecrawl fetches** (primary render + screenshot) | 1 for the main page, plus up to 3 more only if a fee/price/schedule criterion is still unresolved and the bounded navigator runs | `firecrawl_client.py`; navigator bound below |
| **Playwright** (fallback + targeted crops) | Fallback fetch only if Firecrawl fails; plus one short local pass per targeted evidence crop; always used for the final PDF render | `research/` + `report/generator.py` |
| **Bounded navigation** | ≤ **3** fetches total, ≤ **2** hops deep, triggered only for unresolved fee/price/schedule questions; limits are fixed constants, never model-controlled | `evaluator.py` `_NAV_MAX_FETCHES = 3`, `_NAV_MAX_DEPTH = 2` (bounds) |
| **Low-confidence re-check** | ≤1 extra judgment call per finding, only when the model self-reports low confidence on a found/not-found verdict | `evaluator.py::_evaluate_web_criterion` (bound) |
| **Evidence captures written** | 1–7 observed (whole-page + any targeted crops + navigator subpages) | GallopNYC 7, Planet Fitness 3, LaGuardia 3, Weighted Blanket 1 |
| **Typical wall-clock runtime** | *Estimate:* ~30–90s for a normal site; longer when the navigator follows subpages or Firecrawl retries. Firecrawl fetch timeout is 30s per page | *estimate* + `firecrawl_client.py` `timeout_ms=30_000` |

The whole design keeps this bounded and auditable on purpose: a fixed number of
LLM calls per criterion and a hard cap on page fetches, never an open-ended
agent loop that can rack up cost or wander.

## Status

**All 7 categories implemented and all 10 sample applications run live** (real OpenAI + Firecrawl
calls, real provider websites) — see `output/samples/`. Four of them are committed as complete,
validated audit packages (report + PDF + JSON + evidence + manifests) and written up in
[Final sample runs](#final-sample-runs) above: **Sample 01 (GallopNYC)**, **Sample 04 (Planet
Fitness)**, **Sample 08 (Weighted Blanket)**, and **Sample 09 (LaGuardia ACE)**. This also includes
the two adversarial cases the brief calls out by name: Sample 07 (laptop) is deterministically
flagged against the HRI exclusion list ("Computer Hardware"), and Sample 10 (the Gracie Barra
appeal) correctly
re-confirms the website still doesn't show published fees rather than being upgraded by the
appellant's non-web rate sheet. Both of those adversarial cases are now also locked in by a
fixture-based regression test (`tests/unit/test_exclusion_list_regression.py`,
`tests/unit/test_evidence_provenance_regression.py`) that loads the real checklist configs, so a
future code change that breaks either one fails CI immediately instead of waiting for someone to
notice on the next live run.

A non-technical "Manage Checklists" UI (`/manage-checklists`) is also implemented — add or edit a
category through a plain-language wizard instead of hand-authoring YAML; see
[Adding a new form/checklist](#adding-a-new-formchecklist) above.

See `docs/acceptance-criteria-checklist.md` for a literal, item-by-item walkthrough of the brief's
own §8/§9/§10 requirements against this repo's actual state, and `log.md` for the full build
history, including every bug found during manual QA and how it was fixed.

## Limitations and assumptions

- No persistent database — application state lives in memory for the life of the server process
  (by design for this exercise; see the production roadmap below).
- Targeted evidence crops depend on locating the exact quoted text in the rendered DOM; when that
  fails, the tool honestly falls back to labeling the capture as full-page rather than fabricating
  a crop.
- The bounded pricing navigator (above) helps with the most common gap — a price a couple of
  clicks from the homepage — but it is not a general multi-page research system: it only triggers
  for fee/price/schedule-type criteria, follows at most two hops / three pages, doesn't drive
  form interactions (e.g. typing a location into a club-finder), and if no followed page has the
  answer, the finding correctly stays at Needs Review with a plain explanation of what's missing
  rather than guessing a price or browsing indefinitely.
- The checkbox-answer parser reads a fixed, known form layout (YES-then-NO glyphs immediately
  after the question text) — it's not a general PDF form-field reader.
- Only synthetic/sample data is used; production would need PHI-handling controls (field-level
  redaction before any third-party LLM call, audit logging, access control) beyond this exercise's
  scope.
- The LLM's per-criterion judgment is inherently non-deterministic between runs on ambiguous pages
  — this is treated as a feature, not a bug, and is now partly mitigated by the confidence-gated
  re-check above, though that only catches disagreement when the model itself flags low
  confidence, not every possible case of drift.

See `docs/limitations-and-assumptions.md` for the full, itemized version of this list.

## Where this goes next: a production roadmap

Honest gaps identified during this project's own review, proposed here as future work rather than
built now, since each is a real scope/cost decision a team should make deliberately rather than
have made for them silently:

1. **Regression coverage for every category, not just the two adversarial ones.** Sample 07's
   exclusion list and Sample 10's evidence-provenance behavior are now locked in by fixture tests
   (see Status above), but the other five categories' fee-cap logic and category-specific rules
   are currently only exercised by their one live run each in `output/samples/` — a real gap if
   someone edits `fee_match.py` or a shared rule six months from now.
2. **A real datastore and task queue.** In-memory `ApplicationRecord` state means a server
   restart loses any review in progress; a single background thread means one reviewer's research
   run blocks the next. Production needs Postgres (or similar) plus a real queue (Celery/RQ) so
   multiple reviewers can work concurrently.
3. **PHI-handling controls.** Field-level redaction before any third-party LLM call (or a
   private/self-hosted model), encryption at rest, per-reviewer access control, and audit logging
   that meets the agency's actual compliance bar — this exercise uses only synthetic data and
   doesn't need any of that yet, but production would.
4. **Generalized multi-page research.** The bounded pricing navigator (above) already follows
   links up to two hops for fee/price/schedule questions, but a category config still can't
   declare "always check these N pages" up front, and it deliberately stops short of driving
   form interactions (typing a location into a club-finder, for instance). Both would be natural
   next steps once there's evidence they're needed across more categories.
5. **Review-gated, versioned checklist publishing.** Today, anyone with access to
   `/manage-checklists` can publish a checklist change and it goes live immediately, overwriting
   the previous YAML with no history kept. In production, publishing a category should be a
   **reviewed, role-gated, and versioned action**: an author edits and submits a draft, a second
   authorized person (a supervisor/policy owner) reviews the diff against the current live config
   and approves it, and only then does it go live — with the whole approval recorded in the audit
   log and the prior version retained so a bad change can be **rolled back** in one click. The
   current draft/test/publish split is the right shape for this; it just needs authentication,
   roles, an approval step, and per-category version history added on top, so a single user can't
   change how applications are evaluated unilaterally and no edit is unrecoverable.
6. **Monitoring and alerting** on fetch failure rates, LLM error/re-check rates, and per-
   application cost — useful in a single local session, essential once this runs unattended
   against dozens of applications a day.
7. **A scheduled re-verification workflow**, matching the brief's own note that approvals "may be
   spot-checked periodically" — re-running research on a cadence and diffing against the original
   evidence to catch a provider's price change after the fact.

## Running the tests

```bash
uv run pytest -q                    # unit + schema + security (fast, no API calls)
uv run pytest -q -m network          # + tests requiring real DNS/network
uv run pytest -q -m e2e              # full live Sample 01 acceptance test —
                                      # starts a real server, costs real
                                      # OpenAI + Firecrawl API usage
```

