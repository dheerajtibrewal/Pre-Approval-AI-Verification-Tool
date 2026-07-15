"""Turns raw fetch results into on-disk, timestamped EvidenceItem records.

Every evidence image gets a visible date/time + URL watermark burned into the
pixels (Brief §6: "an audit needs to prove what the site showed on that
date"), so the proof survives even if the file's metadata is stripped by a
later copy/export step. Evidence is deduplicated by (url, content hash) within
a single run so re-confirming the same fact twice doesn't create redundant
near-identical files.
"""

from __future__ import annotations

import io
from datetime import timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from preapproval_tool.evidence.models import EvidenceItem
from preapproval_tool.research.models import PageCapture
from preapproval_tool.research.playwright_client import screenshot_element_by_text


def _watermark(image_bytes: bytes, *, url: str, captured_at) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    caption = f"Captured {captured_at.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC  ·  {url}"

    bar_height = 28
    canvas = Image.new("RGB", (img.width, img.height + bar_height), (17, 17, 20))
    canvas.paste(img, (0, 0))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("Helvetica.ttc", 14)
    except OSError:
        font = ImageFont.load_default()
    draw.text((10, img.height + 6), caption, fill=(230, 230, 235), font=font)

    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


class EvidenceCaptureService:
    def __init__(self, run_dir: str | Path):
        self.run_dir = Path(run_dir)
        self.evidence_dir = self.run_dir / "evidence"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self._seen_hashes: dict[str, Path] = {}

    def _write(self, filename: str, watermarked_bytes: bytes, content_hash: str) -> Path:
        if content_hash in self._seen_hashes:
            return self._seen_hashes[content_hash]
        path = self.evidence_dir / filename
        path.write_bytes(watermarked_bytes)
        self._seen_hashes[content_hash] = path
        return path

    def capture_whole_page(self, capture: PageCapture, *, slug: str) -> EvidenceItem:
        content_hash = EvidenceItem.hash_bytes(capture.screenshot_bytes)
        watermarked = _watermark(
            capture.screenshot_bytes, url=capture.final_url, captured_at=capture.fetched_at
        )
        path = self._write(f"whole-page-{slug}-{content_hash}.png", watermarked, content_hash)
        return EvidenceItem(
            evidence_type="whole_page",
            criterion_id=None,
            label="Full page as reviewed",
            url=capture.final_url,
            captured_at=capture.fetched_at,
            method=capture.method,
            file_path=str(path),
            content_hash=content_hash,
            page_title=capture.page_title,
        )

    def capture_targeted(
        self,
        capture: PageCapture,
        *,
        criterion_id: str,
        label: str,
        locate_text: str | None,
    ) -> EvidenceItem | None:
        """Attempt a cropped element screenshot at `locate_text`. Returns
        `None` if the element can't be located — the caller should fall back
        to the shared whole-page evidence in that case rather than this
        method fabricating a second, separately-labeled whole-page capture
        per criterion (that produced a confusing, sometimes self-
        contradictory duplicate — e.g. a "Found" finding paired with a crop
        captioned "no public X clearly visible on the page" — and needlessly
        doubled the number of embedded images, per user QA feedback on
        Sample 10). Never claim a crop that didn't actually happen (PM
        feedback: "never claim a screenshot is targeted unless the relevant
        evidence is clearly readable").
        """
        if not locate_text:
            return None
        element_bytes = screenshot_element_by_text(capture.final_url, locate_text)
        if element_bytes is None:
            return None

        content_hash = EvidenceItem.hash_bytes(element_bytes)
        watermarked = _watermark(
            element_bytes, url=capture.final_url, captured_at=capture.fetched_at
        )
        path = self._write(
            f"criterion-{criterion_id}-{content_hash}.png", watermarked, content_hash
        )
        return EvidenceItem(
            evidence_type="targeted",
            criterion_id=criterion_id,
            label=label,
            url=capture.final_url,
            captured_at=capture.fetched_at,
            method=capture.method,
            file_path=str(path),
            content_hash=content_hash,
            page_title=capture.page_title,
        )
