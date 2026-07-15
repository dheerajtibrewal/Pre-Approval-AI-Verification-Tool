from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class PageCapture:
    """The result of successfully fetching + rendering one URL."""

    url: str
    final_url: str
    text_content: str
    screenshot_bytes: bytes
    fetched_at: datetime
    method: str  # "firecrawl" | "playwright"
    page_title: str = ""
    links: list[str] = field(default_factory=list)  # same-page hrefs, for subpage discovery

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)


@dataclass
class FetchAttempt:
    method: str
    ok: bool
    error: str | None = None


@dataclass
class FetchResult:
    """Outcome of the two-tier fetch strategy for one URL, including diagnostics."""

    url: str
    capture: PageCapture | None
    attempts: list[FetchAttempt] = field(default_factory=list)

    @property
    def accessible(self) -> bool:
        return self.capture is not None
