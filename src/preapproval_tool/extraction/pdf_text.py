"""Deterministic PDF text-layer extraction (no LLM involved at this stage)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pdfplumber


@dataclass
class PdfText:
    full_text: str
    pages: list[str]
    page_count: int

    @property
    def has_text_layer(self) -> bool:
        """False for scanned images with no extractable text — a low-confidence signal."""
        return len(self.full_text.strip()) > 40  # a bare form header is already longer than this


def extract_pdf_text(path: str | Path) -> PdfText:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file, got {path.suffix}")

    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")

    return PdfText(full_text="\n\n".join(pages), pages=pages, page_count=len(pages))
