# AI Conversation

## 1. Tools & Models Used

There are **two very different roles** an AI model can play here, and this
project used several models across both — deliberately, matched to the job:

- **Build-time AI** — the models used to *plan, write, and QA this project*.
- **In-product AI** — the model the *finished tool itself calls at runtime*
  when it researches a provider's website.

Keeping these straight matters: none of the build-time models are shipped or
called by the running product, and the in-product model never wrote a line of
this codebase.

### A. Build-time AI — how this project was designed and built

The build used a deliberate **three-model strategy**, changing models as the
work changed from "think and plan" to "build" to "harden and QA":

1. **ChatGPT (GPT-5.6, "Soul") — the planning / product-management / QA-strategy
   layer.** This is where the project started. GPT-5.6 acted as a *project
   manager and product analyst*: shaping the product thinking, doing QA and
   product analysis, helping scaffold the project structure, and reviewing and
   planning the individual build phases before any code was written. Throughout
   the build it played the "PM giving suggestions" role — pressure-testing
   decisions, proposing what each phase should contain, and reviewing outputs
   from a product standpoint. **Why this model here:** the earliest and highest-
   leverage work is planning and product judgment, not typing code — using a
   strong reasoning model as a dedicated planner/reviewer (separate from the
   agent doing the implementation) keeps a second, independent perspective on
   scope, priorities, and quality.
2. **Claude Code (Sonnet 5, `claude-sonnet-5`) — the primary build agent for the
   core infrastructure.** The base of the system — the deterministic pipeline,
   the checklist engine, extraction, research/evidence layers, the web app, and
   the first rounds of tests — was built with Claude Code running Sonnet 5.
   **Why this model here:** Sonnet 5 is fast and highly capable for sustained,
   high-volume implementation work — writing lots of code and tests across many
   files — which is exactly what standing up the base infrastructure needs.
3. **Claude Code (Opus 4.8, `claude-opus-4-8`) — the final-phase QA, analysis,
   and hardening agent.** For the last phase, the build switched from Sonnet 5
   to Opus 4.8. This phase was less about writing new features and more about a
   rigorous, comprehensive QA pass: finding the loose ends and weak spots in the
   production build, tightening the architecture (e.g. the bounded pricing
   navigator, dead-link recovery, the "what's missing from the form" pricing
   diagnostic, humanized error messages, the grounded report summary, and the
   PDF-report polish), and stress-testing the whole thing end to end. **Why the
   switch:** the final QA/analysis work benefits from the strongest reasoning
   available — Opus 4.8 is both fast and sharper than Sonnet 5 at the kind of
   deep, cross-cutting analysis that catches subtle gaps a feature-building pass
   can miss, so it was the right model for a thorough final review.

**The approach, start to end:** *plan and product-review with GPT-5.6 → build
the base with Sonnet 5 → harden, analyze, and QA with Opus 4.8.* Each model was
chosen for what that stage of the work actually demanded — reasoning/planning,
then throughput, then depth of analysis — rather than using one model for
everything. See `AI-CONVERSATION.md` §2 for the real transcripts and `log.md`
for the phase-by-phase engineering diary.

### B. In-product AI & tooling — what the finished tool calls at runtime

- **OpenAI GPT-4o** (`OPENAI_MODEL=gpt-4o`, see `.env.example`) — the *only*
  model the running product itself calls, and always as a **bounded,
  schema-validated tool inside fixed pipeline stages**
  (`src/preapproval_tool/llm/client.py`), never as a free agent. Its jobs:
  1. **Structured field extraction** — turning the PDF's raw text into
     structured fields (participant, provider, item, URL, fee), JSON-schema
     validated before use.
  2. **Category-classification fallback** — only when deterministic template
     matching is ambiguous; otherwise no model is involved in categorization.
  3. **Grounded per-criterion website judgment** — deciding whether a page's
     text supports a criterion, and it *must* cite an exact quote that is then
     independently verified against the real captured page text (an unverifiable
     quote gets the finding held at Needs Review).
  4. **Link ranking for the pricing navigator** — choosing which real,
     already-discovered same-site links are most likely to hold a missing price,
     so the navigator follows good pages (e.g. `/become-a-member`) a keyword
     list would miss. It only *re-orders real URLs*; it never fetches or invents.
  5. **The report's plain-language summary** — generated strictly from the
     already-computed findings (never raw website text), told to restate them
     without adding facts or making an approve/deny decision, and optional (a
     failed call just falls back to a deterministic templated line).

  **Why GPT-4o:** strong instruction-following against strict output schemas
  (every call is JSON-schema-validated before the result is trusted downstream)
  and fast/cheap enough to run several bounded calls per application without the
  tool feeling slow. It is never the thing that decides *whether* a screenshot
  was taken or that sets a status — only *what a page's text means* — which is
  the core anti-hallucination design of the whole system.
- **Firecrawl** — primary fetch/render API for provider websites (handles
  JS rendering and anti-bot bypass server-side); returns clean text, the page's
  links, and a full-page screenshot in one call.
- **Playwright (Chromium)** — fallback fetch when Firecrawl fails, the mechanism
  for targeted (per-criterion) evidence crops (Firecrawl doesn't return DOM
  element coordinates), and the renderer for the exported PDF report.
- **pdfplumber** — deterministic PDF text-layer extraction (not AI); feeds the
  GPT-4o extraction step and the regex-based checkbox-answer parser.

*(Bottom line on roles: **GPT-5.6, Sonnet 5, and Opus 4.8 built this project**
— planning, coding, and QA respectively — while **GPT-4o is the only model the
finished product calls at runtime**, and even then only as a tightly bounded,
schema-validated tool. All are disclosed because all shaped how this was
engineered.)*

## 2. The conversations (full transcripts)

The complete, unedited AI conversations behind this build are committed in
[`docs/ai-transcripts/`](docs/ai-transcripts/). They are kept as separate files
rather than pasted inline here because they are long and span two different AI
tools used for two different jobs (see §1) — this file stays a readable guide,
and the raw record lives alongside it:

| Transcript | Tool / role | What it covers |
|---|---|---|
| [`docs/ai-transcripts/gptchat_raw_project_thread.md`](docs/ai-transcripts/gptchat_raw_project_thread.md) | ChatGPT (GPT‑5.6 "Soul") — project manager / product analysis / QA strategy / phase planning | The planning-and-review thread: requirement analysis of the brief, phase plans, QA punch-lists, and the acceptance criteria the build was held to. |
| [`docs/ai-transcripts/claude-code-build-transcript.md`](docs/ai-transcripts/claude-code-build-transcript.md) | Claude Code (Sonnet 5 → Opus 4.8) — the engineer that wrote the code | The full build session: scaffolding, every phase of implementation, the live QA passes on the sample runs, and the bug fixes they surfaced. |

**About the Claude Code transcript:** it is a **text-only** export produced from
the raw Claude Code session log. Pasted screenshots/images and heavy tool
payloads have been removed (they made the raw log ~175 MB); each tool call is
preserved as a single `→ [Tool] summary` line so the flow of work stays
readable end to end. Nothing in the *conversation* itself — prompts, reasoning,
corrections, dead ends, back-and-forth — has been paraphrased or tidied. It is
the real, imperfect record, which is the point: this file exists to show how the
work was actually done with AI, not to re-grade the code.

The `log.md` "Progress timeline" is the phase-by-phase index into that build
transcript.
