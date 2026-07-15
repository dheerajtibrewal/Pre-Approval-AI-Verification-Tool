"""Typed representation of a checklist config file (config/checklists/*.yaml)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Verifiable = Literal["web", "internal", "document"]
CheckType = Literal["rule", "llm_judgment", "fee_match", "exclusion_list"]
FieldType = Literal["string", "number", "currency", "url", "date"]


class FormField(BaseModel):
    id: str
    label: str
    type: FieldType
    required: bool = True
    pii: bool = False


class Criterion(BaseModel):
    id: str
    question: str
    verifiable: Verifiable
    check_type: CheckType
    evidence_label: str = ""
    exclusion_list: list[str] = Field(default_factory=list)
    caps: dict[str, float] = Field(default_factory=dict)
    notes: str = ""
    explanation: str = ""
    group: str = "Other internal requirements"
    form_question: str = ""

    @property
    def form_question_text(self) -> str:
        return self.form_question or self.question

    @property
    def is_web_verifiable(self) -> bool:
        return self.verifiable == "web"


class ChecklistConfig(BaseModel):
    category_id: str
    display_name: str
    appeal_of: str | None = None
    form_template_signature: list[str]
    item_name_field: str | None = None
    fee_field: str | None = None
    fields: list[FormField]
    criteria: list[Criterion]

    @property
    def web_criteria(self) -> list[Criterion]:
        return [c for c in self.criteria if c.verifiable == "web"]

    @property
    def internal_criteria(self) -> list[Criterion]:
        return [c for c in self.criteria if c.verifiable != "web"]

    def field(self, field_id: str) -> FormField | None:
        return next((f for f in self.fields if f.id == field_id), None)

    def criterion(self, criterion_id: str) -> Criterion | None:
        return next((c for c in self.criteria if c.id == criterion_id), None)
