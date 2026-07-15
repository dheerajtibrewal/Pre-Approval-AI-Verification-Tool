#!/usr/bin/env python3
"""Run the full pipeline on one application PDF and write a complete committed
report package to an output directory — no web UI needed. The package contains
report.html + report.pdf + report.json + evidence-manifest.json +
run-metadata.json + evidence/ (the same bundle the in-app export produces).

Usage:
    uv run python scripts/run_sample.py samples/Sample-01---Community-Class-GallopNYC.pdf \
        output/samples/sample-01-gallopnyc --category community-classes

If --category is omitted, the deterministic/LLM classifier decides.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from preapproval_tool.categorization.classifier import CategoryAmbiguousError, classify  # noqa: E402
from preapproval_tool.checklist_engine.loader import load_all_checklists  # noqa: E402
from preapproval_tool.evaluation.evaluator import run_evaluation  # noqa: E402
from preapproval_tool.evidence.capture_service import EvidenceCaptureService  # noqa: E402
from preapproval_tool.extraction.field_extractor import extract_fields  # noqa: E402
from preapproval_tool.extraction.pdf_text import extract_pdf_text  # noqa: E402
from preapproval_tool.report.generator import build_report_data, write_report_package  # noqa: E402
from preapproval_tool.web.export import write_full_package  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--category", help="Force a category_id instead of auto-classifying.")
    parser.add_argument(
        "--denial-reason-field",
        default="denial_reason",
        help="Field id holding the appeal's denial reason, if this is an appeals form.",
    )
    args = parser.parse_args()

    print(f"[1/6] Reading {args.pdf_path.name} ...")
    pdf_text = extract_pdf_text(args.pdf_path)

    checklists = load_all_checklists()
    if args.category:
        category_id = args.category
    else:
        try:
            result = classify(pdf_text.full_text)
        except CategoryAmbiguousError as exc:
            print(f"ERROR: category ambiguous — {exc}. Candidates: {exc.candidates}")
            sys.exit(1)
        category_id = result.category_id
        print(f"[2/6] Category: {category_id} (via {result.method}, {result.confidence} confidence)")

    checklist = checklists[category_id]

    print("[3/6] Extracting fields via LLM ...")
    extracted = extract_fields(checklist, pdf_text)
    if extracted.low_confidence_fields:
        print(f"  low-confidence fields: {extracted.low_confidence_fields}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[4/6] Researching website + capturing evidence into {args.output_dir} ...")
    capture_service = EvidenceCaptureService(args.output_dir)
    evaluation = run_evaluation(checklist, extracted, capture_service)

    print("[5/6] Building report ...")
    appeal_reason = extracted.value(args.denial_reason_field) if checklist.appeal_of else None
    report = build_report_data(
        checklist,
        extracted,
        evaluation,
        application_id=args.pdf_path.stem,
        appeal_denial_reason=appeal_reason,
    )
    out_path = write_report_package(report, args.output_dir)
    # Full committable package: report.pdf, report.json, evidence-manifest.json,
    # run-metadata.json — same builders the in-app export uses, so an offline
    # committed sample and a reviewer's downloaded audit zip never drift.
    write_full_package(report, args.output_dir)

    manifest = {
        "source_pdf": args.pdf_path.name,
        "category_id": checklist.category_id,
        "generated_at": report.generated_at.isoformat(),
        "summary_counts": report.summary_counts,
        "internal_criteria_count": len(report.internal_findings),
        "fetch_error": evaluation.fetch_error,
        "low_confidence_fields": extracted.low_confidence_fields,
    }
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    print(f"[6/6] Done. Report: {out_path}")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
