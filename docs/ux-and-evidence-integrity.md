# UX and Evidence-Integrity Notes

## Problem addressed

The original (Phase 2) report was a single, uninterrupted vertical scroll
mixing plain-language summary, 20 checklist criteria, and evidence
screenshots in one flat page. It technically showed everything required, but
a non-technical reviewer had to read the whole thing top-to-bottom to
understand what needed their attention, and reviewer edits (status
overrides) were silently lost the moment the reviewer clicked "Regenerate."
This document covers the redesign that addressed both problems.

## Information architecture

Five tabs, chosen to match how a reviewer actually works through an
application rather than how the data happens to be structured internally:

1. **Overview** — answers "what was requested, what did the site confirm,
   what needs my attention" in under 30 seconds, before any detail.
2. **Findings** — the detailed per-criterion work, filterable/searchable,
   collapsed by default (progressive disclosure) so 20 items don't read as
   one wall of text.
3. **Evidence** — every capture as a first-class, browsable object with its
   own metadata, decoupled from any one finding.
4. **Internal Checks** — deliberately separated from Findings so a reviewer
   never mistakes "can't check this from a website" for "failed check."
5. **Review & Export** — the terminal action: is this ready to hand off, and
   how do I get it out of the tool.

Tabs are implemented client-side (no server round-trip to switch), synced to
`location.hash` so the browser back button and deep-linking both work, and
built as a real ARIA `tablist`/`tab`/`tabpanel` trio with arrow-key
navigation — not a set of styled `<div>`s.

## Design principles

- **Restraint over decoration.** One accent color, four semantic status
  colors, a single 8px-multiple spacing scale, system font stack. No
  gradients, no glass effects, no more than one level of card nesting.
- **Progressive disclosure.** A finding's one-line summary is always
  visible; the quote, evidence thumbnails, and edit controls are behind an
  explicit expand — the reviewer chooses how deep to go per item.
- **Status is never color-only.** Every badge carries a text label
  ("Found", "Needs Review", etc.) alongside its color.
- **Calm motion.** The only animations are the tab-chevron rotation and a
  loading spinner on the progress screen, both disabled under
  `prefers-reduced-motion`.

## Evidence rules

- A finding can be "Found" only if it has at least one real, on-disk
  evidence capture — enforced structurally in `Finding.__post_init__`, not
  just by prompt instruction.
- An LLM-provided quote is independently re-verified against the actual
  captured page text (`is_quote_grounded`) before it's used as grounding for
  anything; an unverified quote downgrades the finding to Needs Review and
  is dropped rather than displayed as if it were confirmed.
- A "targeted" evidence label is only used when a real, distinct crop was
  captured; otherwise the capture is honestly labeled as full-page.
- Every evidence item displays its source URL, page title (when available),
  capture timestamp, evidence ID (a content hash — also used for dedup), and
  which finding(s) reference it.
- `web/export.py::validate_export` re-checks all of the above at export
  time, independent of the construction-time guarantees, specifically so a
  future refactor bug upstream can't silently produce an unvalidated
  package.

## Reviewer workflow

- Every finding supports three actions: override (change status + note),
  mark reviewed (confirm as-is), and restore (revert to the system's
  original result).
- The system's original result is never overwritten — `original_status`/
  `original_note` are preserved the first time an override is applied, and
  every action is appended to a per-finding `history` list with a
  timestamp, giving a real (if in-memory) audit trail.
- Reviewer decisions are stored independently of the `Finding` objects
  themselves (`ApplicationRecord.review_state`), specifically so
  "Regenerate report" — which re-runs the live website research from
  scratch — can rebuild fresh findings and then reapply prior reviewer
  decisions on top, rather than losing them.

## Responsive behaviour

Verified with real (Playwright-driven) passes at 390px, 768px, and 1280px:
no horizontal overflow at any width; the left sidebar becomes a horizontal,
scrollable tab bar under 900px; evidence thumbnails and the extraction-
confirmation field grid both collapse to a single column on narrow screens.

## Accessibility decisions

- Tabs: ARIA `tablist`/`tab`/`tabpanel`, `aria-selected`, roving `tabindex`,
  and arrow-key switching.
- Evidence viewer: a native `<dialog>` element — gets focus containment,
  Escape-to-close, and an inert background for free from the browser, rather
  than a hand-rolled modal.
- Every status badge pairs an icon/text label with its color.
- All form inputs have associated `<label>` elements (including the
  filter/search controls, which use visually-hidden labels).
- `:focus-visible` outlines are visible in both light and dark mode;
  `prefers-reduced-motion` disables the loading spinner's animation and all
  CSS transitions.

## Known limitations of this pass

- No automated axe-core/Lighthouse audit was run; the above is a manual,
  practical WCAG 2.2 AA pass verified via keyboard navigation and real
  browser testing, not a certified accessibility audit.
- All 7 categories now run through this same UI (Phase 3 added the
  remaining 6 checklist configs), confirming the UI genuinely has no
  category-specific code — but the full interactive reviewer-action pass
  (override/mark-reviewed/restore, refresh persistence, regenerate) was only
  re-verified end-to-end for Sample 01; the other 9 samples were verified as
  non-interactive report generations (`scripts/run_sample.py`), not through
  the full live reviewer workflow.
