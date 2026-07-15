"""In-memory application store — deliberately no database for this build.

Each uploaded application gets a run directory under RUN_OUTPUT_DIR holding
its evidence captures and report. State lives only for the life of the
process; see docs/limitations-and-assumptions.md for what a persistent store
would add for production.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from preapproval_tool.checklist_engine.models import ChecklistConfig
from preapproval_tool.evaluation.evaluator import EvaluationRun
from preapproval_tool.evaluation.models import Finding
from preapproval_tool.extraction.models import ExtractedApplication
from preapproval_tool.report.models import ReportData

RUN_OUTPUT_DIR = Path(os.environ.get("RUN_OUTPUT_DIR", "output/runs"))


@dataclass
class ApplicationRecord:
    id: str
    pdf_filename: str
    pdf_path: Path
    run_dir: Path
    stage: str = "extracted"  # extracted -> researching -> reported | failed
    progress_message: str = ""
    progress_error: str = ""
    checklist: ChecklistConfig | None = None
    extracted: ExtractedApplication | None = None
    evaluation: EvaluationRun | None = None
    report: ReportData | None = None
    classification_note: str = ""
    original_extracted_values: dict[str, Any] = field(default_factory=dict)

    # Reviewer decisions survive report regeneration and process-lifetime page
    # refreshes because they live here, independent of the Finding objects a
    # fresh evaluation run rebuilds from scratch. Keyed by criterion_id.
    review_state: dict[str, dict[str, Any]] = field(default_factory=dict)

    def record_override(self, criterion_id: str, *, status: str, note: str) -> None:
        existing = self.review_state.get(criterion_id, {"history": []})
        existing["status"] = status
        existing["note"] = note
        existing["reviewed"] = True
        existing["action"] = "override"
        self.review_state[criterion_id] = existing

    def record_mark_reviewed(self, criterion_id: str, *, status: str, note: str) -> None:
        existing = self.review_state.get(criterion_id, {"history": []})
        existing.setdefault("status", status)
        existing.setdefault("note", note)
        existing["reviewed"] = True
        existing["action"] = existing.get("action", "mark_reviewed")
        self.review_state[criterion_id] = existing

    def clear_override(self, criterion_id: str) -> None:
        self.review_state.pop(criterion_id, None)

    def reapply_review_state(self, findings: list[Finding]) -> None:
        """Called after every fresh evaluation run (including regenerate) to
        restore reviewer decisions onto the newly-built Finding objects. The
        fresh system result is preserved as original_status/original_note
        before the persisted reviewer decision is layered on top.
        """
        for f in findings:
            state = self.review_state.get(f.criterion_id)
            if not state:
                continue
            if state.get("action") == "override" and "status" in state:
                f.apply_reviewer_override(status=state["status"], note=state["note"])
            elif state.get("reviewed"):
                f.mark_reviewed()


class ApplicationStore:
    def __init__(self) -> None:
        self._records: dict[str, ApplicationRecord] = {}

    def new(self, pdf_filename: str, pdf_bytes: bytes) -> ApplicationRecord:
        app_id = uuid.uuid4().hex[:10]
        run_dir = RUN_OUTPUT_DIR / app_id
        run_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = run_dir / "source.pdf"
        pdf_path.write_bytes(pdf_bytes)
        record = ApplicationRecord(
            id=app_id, pdf_filename=pdf_filename, pdf_path=pdf_path, run_dir=run_dir
        )
        self._records[app_id] = record
        return record

    def get(self, app_id: str) -> ApplicationRecord | None:
        return self._records.get(app_id)


store = ApplicationStore()
