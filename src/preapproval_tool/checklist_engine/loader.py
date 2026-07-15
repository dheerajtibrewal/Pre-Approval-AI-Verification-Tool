"""Loads and validates config/checklists/*.yaml against config/checklist_schema.json.

This is the one place category configs are read. Nothing in the rest of the
pipeline should special-case a category name — everything category-specific
lives in these YAML files. Adding a new form/checklist means adding one file
here (see docs/adding-a-checklist.md), not touching this loader.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

import yaml
from jsonschema import Draft7Validator

from preapproval_tool.checklist_engine.models import ChecklistConfig

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKLISTS_DIR = REPO_ROOT / "config" / "checklists"
SCHEMA_PATH = REPO_ROOT / "config" / "checklist_schema.json"


class ChecklistConfigError(ValueError):
    """Raised when a checklist YAML file fails schema or model validation."""


@functools.lru_cache(maxsize=1)
def _schema_validator() -> Draft7Validator:
    schema = json.loads(SCHEMA_PATH.read_text())
    Draft7Validator.check_schema(schema)
    return Draft7Validator(schema)


def _load_one(path: Path) -> ChecklistConfig:
    raw = yaml.safe_load(path.read_text())
    errors = sorted(_schema_validator().iter_errors(raw), key=lambda e: e.path)
    if errors:
        messages = "; ".join(f"{list(e.path)}: {e.message}" for e in errors)
        raise ChecklistConfigError(f"{path.name} failed schema validation: {messages}")
    return ChecklistConfig.model_validate(raw)


def _apply_appeal_reuse(configs: dict[str, ChecklistConfig]) -> None:
    """An appeal must re-run its base category's EXACT website checks, not a
    hand-copied mirror that can silently drift (Sample 02 vs 10 QA: a copied
    criterion had lost its `form_question`, so the checkbox parser matched
    differently). Rather than trust the appeal YAML's copy, the loader replaces
    an appeal's web criteria with the base category's web criteria verbatim,
    keeping the appeal's own non-web criteria (internal checks + the
    appeal-review item). This makes cross-config drift structurally impossible.
    """
    for cid, config in list(configs.items()):
        base_id = config.appeal_of
        if not base_id or base_id not in configs:
            continue
        base = configs[base_id]
        base_web = [c for c in base.criteria if c.verifiable == "web"]
        appeal_non_web = [c for c in config.criteria if c.verifiable != "web"]
        configs[cid] = config.model_copy(update={"criteria": base_web + appeal_non_web})


@functools.lru_cache(maxsize=1)
def load_all_checklists() -> dict[str, ChecklistConfig]:
    """Load + validate every checklist config. Cached — configs are static per process."""
    if not CHECKLISTS_DIR.exists():
        raise FileNotFoundError(f"No checklist config directory at {CHECKLISTS_DIR}")
    configs: dict[str, ChecklistConfig] = {}
    for path in sorted(CHECKLISTS_DIR.glob("*.yaml")):
        config = _load_one(path)
        if config.category_id in configs:
            raise ChecklistConfigError(
                f"Duplicate category_id '{config.category_id}' in {path.name}"
            )
        configs[config.category_id] = config
    _apply_appeal_reuse(configs)
    return configs


def get_checklist(category_id: str) -> ChecklistConfig:
    configs = load_all_checklists()
    if category_id not in configs:
        raise KeyError(
            f"Unknown category_id '{category_id}'. Known: {sorted(configs)}"
        )
    return configs[category_id]
