from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

EvidenceType = Literal["whole_page", "targeted"]


@dataclass
class EvidenceItem:
    evidence_type: EvidenceType
    criterion_id: str | None  # None for whole-page/run-level captures
    label: str
    url: str
    captured_at: datetime
    method: str  # "firecrawl" | "playwright"
    file_path: str
    content_hash: str
    page_title: str = ""

    @property
    def evidence_id(self) -> str:
        """Stable, human-shareable identifier for this capture — the content
        hash already uniquely identifies the file, so it doubles as the ID
        rather than introducing a second, unrelated identifier scheme.
        """
        return self.content_hash

    @staticmethod
    def hash_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()[:16]
