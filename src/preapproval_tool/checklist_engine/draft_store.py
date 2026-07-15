"""Disk-backed storage for in-progress "Manage Checklists" drafts.

Deliberately NOT under config/checklists/ — that directory is only ever read
by `checklist_engine.loader.load_all_checklists()` via a `*.yaml` glob, and
keeping drafts in a separate directory entirely means a future change to
that glob (e.g. to `**/*.yaml`) can never accidentally treat an unpublished,
unreviewed draft as live config.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DRAFTS_DIR = Path(os.environ.get("CHECKLIST_DRAFTS_DIR", "data/checklist_drafts"))


@dataclass
class ChecklistDraft:
    id: str
    wizard: dict[str, Any]
    created_at: str
    updated_at: str
    source_category_id: str | None = None  # set if this draft edits an existing live category
    last_test_summary: dict[str, Any] | None = field(default=None)


class DraftStore:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or DRAFTS_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, draft_id: str) -> Path:
        return self.base_dir / f"{draft_id}.json"

    def new(self, wizard: dict[str, Any], *, source_category_id: str | None = None) -> ChecklistDraft:
        now = datetime.now(timezone.utc).isoformat()
        draft = ChecklistDraft(
            id=uuid.uuid4().hex[:10],
            wizard=wizard,
            created_at=now,
            updated_at=now,
            source_category_id=source_category_id,
        )
        self.save(draft)
        return draft

    def save(self, draft: ChecklistDraft) -> None:
        draft.updated_at = datetime.now(timezone.utc).isoformat()
        self._path(draft.id).write_text(json.dumps(asdict(draft), indent=2))

    def get(self, draft_id: str) -> ChecklistDraft | None:
        path = self._path(draft_id)
        if not path.exists():
            return None
        return ChecklistDraft(**json.loads(path.read_text()))

    def delete(self, draft_id: str) -> None:
        path = self._path(draft_id)
        if path.exists():
            path.unlink()

    def list_all(self) -> list[ChecklistDraft]:
        drafts = [
            ChecklistDraft(**json.loads(p.read_text()))
            for p in sorted(self.base_dir.glob("*.json"))
        ]
        return sorted(drafts, key=lambda d: d.updated_at, reverse=True)


draft_store = DraftStore()
