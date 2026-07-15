import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft7Validator

from preapproval_tool.checklist_engine.loader import (
    ChecklistConfigError,
    _load_one,
    load_all_checklists,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "config" / "checklist_schema.json"
COMMUNITY_CLASSES = REPO_ROOT / "config" / "checklists" / "community-classes.yaml"


def test_schema_itself_is_valid_json_schema():
    schema = json.loads(SCHEMA_PATH.read_text())
    Draft7Validator.check_schema(schema)


def test_community_classes_config_loads_and_validates():
    configs = load_all_checklists()
    assert "community-classes" in configs
    cfg = configs["community-classes"]
    assert len(cfg.web_criteria) == 8
    assert len(cfg.internal_criteria) == 12


def test_missing_required_field_fails_validation(tmp_path):
    broken = yaml.safe_load(COMMUNITY_CLASSES.read_text())
    del broken["criteria"]  # required by the schema
    broken_path = tmp_path / "broken.yaml"
    broken_path.write_text(yaml.dump(broken))
    with pytest.raises(ChecklistConfigError):
        _load_one(broken_path)


ALL_CATEGORY_IDS = {
    "community-classes",
    "coaching",
    "memberships",
    "hri",
    "otps",
    "transition-program",
    "appeals",
}


def test_all_seven_categories_present_and_load():
    """Guards the brief's own "adding a category needs no core rewrite"
    promise: every category the brief lists must have a config file that
    loads cleanly. If a new category is added without a fixture/test, CI
    should fail here as a reminder — not silently.
    """
    configs = load_all_checklists()
    assert set(configs) == ALL_CATEGORY_IDS


def test_every_category_has_at_least_one_web_and_one_internal_criterion():
    configs = load_all_checklists()
    for category_id, cfg in configs.items():
        assert cfg.web_criteria, f"{category_id} has no website-verifiable criteria"
        assert cfg.internal_criteria, f"{category_id} has no internal/document criteria"


def test_appeals_config_references_its_base_category():
    configs = load_all_checklists()
    appeals = configs["appeals"]
    assert appeals.appeal_of == "community-classes"
    assert appeals.appeal_of in configs


def test_exclusion_list_categories_have_a_populated_exclusion_list():
    configs = load_all_checklists()
    for category_id in ("hri", "otps"):
        cfg = configs[category_id]
        exclusion_criteria = [c for c in cfg.criteria if c.check_type == "exclusion_list"]
        assert exclusion_criteria, f"{category_id} has no exclusion_list criterion"
        for c in exclusion_criteria:
            assert c.exclusion_list, f"{category_id}.{c.id} has an empty exclusion_list"


def test_invalid_verifiable_enum_fails_validation(tmp_path):
    broken = yaml.safe_load(COMMUNITY_CLASSES.read_text())
    broken["criteria"][0]["verifiable"] = "not-a-real-option"
    broken_path = tmp_path / "broken.yaml"
    broken_path.write_text(yaml.dump(broken))
    with pytest.raises(ChecklistConfigError):
        _load_one(broken_path)


def test_every_criterion_has_a_group_or_is_web_verifiable():
    """Internal criteria should carry a specific explanation/group rather than
    falling back to generic boilerplate silently for every item (PM feedback).
    """
    cfg = load_all_checklists()["community-classes"]
    for c in cfg.internal_criteria:
        assert c.explanation, f"{c.id} has no criterion-specific explanation"
        assert c.group and c.group != "Other internal requirements", f"{c.id} has no specific group"
