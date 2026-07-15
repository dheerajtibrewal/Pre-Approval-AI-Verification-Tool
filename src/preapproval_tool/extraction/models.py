from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ExtractedApplication(BaseModel):
    category_id: str
    values: dict[str, Any] = Field(default_factory=dict)
    low_confidence_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    raw_text_length: int = 0
    checkbox_answers: dict[str, str | None] = Field(default_factory=dict)

    def value(self, field_id: str) -> Any:
        return self.values.get(field_id)
