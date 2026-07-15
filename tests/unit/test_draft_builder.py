"""The "Manage Checklists" wizard-to-config translation layer. This is the
one place that hides check_type/verifiable vocabulary from a non-technical
user, so it carries the most risk of silently producing an invalid or
wrong-shaped config.
"""

from preapproval_tool.checklist_engine.draft_builder import (
    validate_wizard,
    wizard_from_checklist_config,
)
from preapproval_tool.checklist_engine.loader import load_all_checklists
from preapproval_tool.checklist_engine.models import ChecklistConfig


def _minimal_wizard() -> dict:
    return {
        "category_display_name": "Home Modifications",
        "category_id": "",
        "signature_phrases": ["Home Modification Pre-approval Form"],
        "fields": [
            {"label": "Participant's Name", "type": "text", "pii": True},
            {"label": "Item Requested", "type": "text", "pii": False},
            {"label": "Fee", "type": "money", "pii": False},
        ],
        "questions": [
            {
                "text": "Does the linked page show the item with a visible price?",
                "checkable_from_website": "yes",
                "web_check_kind": "general_judgment",
            },
            {
                "text": "Is the item on the exclusion list?",
                "checkable_from_website": "yes",
                "web_check_kind": "exclusion_list",
                "item_field_label": "Item Requested",
                "exclusion_terms": ["Computer Hardware", "Cell Phones"],
            },
            {
                "text": "Is the published price within the cap?",
                "checkable_from_website": "yes",
                "web_check_kind": "price_compare",
                "price_field_label": "Fee",
                "price_rule": "not_exceed",
                "price_value": "500",
            },
            {
                "text": "Is this approved in the budget?",
                "checkable_from_website": "internal",
                "why_not_checkable": "Requires the approved budget record.",
                "group": "Budget and funding",
            },
        ],
    }


def test_minimal_wizard_produces_valid_config():
    config_dict, errors = validate_wizard(_minimal_wizard())
    assert errors == []
    assert config_dict is not None
    cfg = ChecklistConfig.model_validate(config_dict)
    assert cfg.category_id == "home-modifications"
    assert len(cfg.web_criteria) == 3
    assert len(cfg.internal_criteria) == 1
    assert cfg.fee_field is not None
    assert cfg.item_name_field is not None


def test_exclusion_criterion_carries_terms_through():
    config_dict, errors = validate_wizard(_minimal_wizard())
    assert errors == []
    exclusion_criteria = [c for c in config_dict["criteria"] if c["check_type"] == "exclusion_list"]
    assert len(exclusion_criteria) == 1
    assert "Computer Hardware" in exclusion_criteria[0]["exclusion_list"]


def test_price_compare_cap_mode_maps_to_max_key():
    config_dict, errors = validate_wizard(_minimal_wizard())
    assert errors == []
    fee_criteria = [c for c in config_dict["criteria"] if c["check_type"] == "fee_match"]
    assert fee_criteria[0]["caps"] == {"max": 500.0}


def test_missing_category_name_is_a_plain_language_error():
    wizard = _minimal_wizard()
    wizard["category_display_name"] = ""
    config_dict, errors = validate_wizard(wizard)
    assert config_dict is None
    assert any("name" in e.lower() for e in errors)


def test_missing_exclusion_terms_is_a_plain_language_error():
    wizard = _minimal_wizard()
    wizard["questions"][1]["exclusion_terms"] = []
    config_dict, errors = validate_wizard(wizard)
    assert config_dict is None
    assert any("excluded item" in e.lower() for e in errors)


def test_no_questions_is_an_error():
    wizard = _minimal_wizard()
    wizard["questions"] = []
    config_dict, errors = validate_wizard(wizard)
    assert config_dict is None
    assert any("question" in e.lower() for e in errors)


def test_duplicate_question_text_gets_unique_criterion_ids():
    wizard = _minimal_wizard()
    wizard["questions"] = [
        {
            "text": "Is this approved in the budget?",
            "checkable_from_website": "internal",
            "why_not_checkable": "Requires the approved budget record.",
        },
        {
            "text": "Is this approved in the budget?",
            "checkable_from_website": "internal",
            "why_not_checkable": "Duplicate wording, different criterion.",
        },
    ]
    config_dict, errors = validate_wizard(wizard)
    assert errors == []
    ids = [c["id"] for c in config_dict["criteria"]]
    assert len(ids) == len(set(ids))


def test_round_trip_wizard_from_existing_live_category():
    """Editing a real, hand-authored config through the wizard must produce
    a config that still validates cleanly — this is the "update an existing
    category" half of the feature.
    """
    live = load_all_checklists()
    cfg = live["community-classes"]
    wizard = wizard_from_checklist_config(cfg)
    config_dict, errors = validate_wizard(wizard)
    assert errors == [], errors
    assert config_dict["category_id"] == "community-classes"
    assert len(config_dict["criteria"]) == len(cfg.criteria)
