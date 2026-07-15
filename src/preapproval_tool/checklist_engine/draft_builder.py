"""Translates the plain-language "Manage Checklists" wizard form into a
schema-valid checklist config dict (and back again, for editing an existing
live category). This is the one place that hides `check_type`/`verifiable`
vocabulary from a non-technical user — everything downstream (the loader,
evaluator, report generator) still only ever sees an ordinary
config/checklists/*.yaml-shaped dict, so no other module needs to know this
wizard exists.
"""

from __future__ import annotations

import re
from typing import Any

from preapproval_tool.checklist_engine.models import ChecklistConfig

_FIELD_TYPE_LABELS = {
    "text": "string",
    "number": "number",
    "money": "currency",
    "link": "url",
    "date": "date",
}
_FIELD_TYPE_LABELS_REVERSE = {v: k for k, v in _FIELD_TYPE_LABELS.items()}


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "item"


def _unique_slug(base: str, taken: set[str]) -> str:
    slug = slugify(base)
    candidate = slug
    n = 2
    while candidate in taken:
        candidate = f"{slug}-{n}"
        n += 1
    taken.add(candidate)
    return candidate


def _friendly(msg: str) -> str:
    return msg


def validate_wizard(wizard: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    """Returns (config_dict, errors). config_dict is None if errors is non-empty.

    Plain-language checks first (these are the errors a non-technical user
    will actually hit); only falls back to a generic message for anything
    unexpected that slips past them.
    """
    errors: list[str] = []

    display_name = (wizard.get("category_display_name") or "").strip()
    if not display_name:
        errors.append("Please give this category a name.")

    category_id = slugify(wizard.get("category_id") or display_name)
    if not category_id or category_id == "item":
        errors.append("Please give this category a name so it can be identified internally.")

    signature_phrases = [p.strip() for p in (wizard.get("signature_phrases") or []) if p and p.strip()]
    if not signature_phrases:
        errors.append(
            "Please add at least one phrase that always appears on this form "
            "(e.g. its title line) — this is how the tool recognizes it."
        )

    raw_fields = wizard.get("fields") or []
    fields: list[dict[str, Any]] = []
    field_ids_by_label: dict[str, str] = {}
    taken_field_ids: set[str] = set()
    for i, f in enumerate(raw_fields, start=1):
        label = (f.get("label") or "").strip()
        if not label:
            errors.append(f"Field #{i}: please give it a name (what it's called on the form).")
            continue
        wizard_type = f.get("type") or "text"
        if wizard_type not in _FIELD_TYPE_LABELS:
            errors.append(f"Field '{label}': please choose a valid field type.")
            continue
        field_id = _unique_slug(label, taken_field_ids)
        field_ids_by_label[label] = field_id
        fields.append(
            {
                "id": field_id,
                "label": label,
                "type": _FIELD_TYPE_LABELS[wizard_type],
                "pii": bool(f.get("pii", False)),
            }
        )
    if not fields:
        errors.append("Please add at least one field to extract from the form (e.g. participant name).")

    raw_questions = wizard.get("questions") or []
    criteria: list[dict[str, Any]] = []
    taken_criterion_ids: set[str] = set()
    fee_field: str | None = None
    item_name_field: str | None = None

    for i, q in enumerate(raw_questions, start=1):
        text = (q.get("text") or "").strip()
        if not text:
            errors.append(f"Question #{i}: please enter the question as it appears on the form.")
            continue
        checkable = q.get("checkable_from_website")
        criterion_id = _unique_slug(text, taken_criterion_ids)
        base = {
            "id": criterion_id,
            "question": text,
            "notes": (q.get("notes") or "").strip(),
            "group": (q.get("group") or "").strip() or "Other internal requirements",
        }

        if checkable == "yes":
            kind = q.get("web_check_kind")
            if kind == "general_judgment":
                criteria.append(
                    {
                        **base,
                        "verifiable": "web",
                        "check_type": "llm_judgment",
                        "evidence_label": f"Evidence: {text[:60]}",
                    }
                )
            elif kind == "price_compare":
                price_field_label = q.get("price_field_label")
                field_id = field_ids_by_label.get(price_field_label or "")
                if not field_id:
                    errors.append(
                        f"Question '{text[:60]}': please choose which field holds the form's price."
                    )
                    continue
                rule = q.get("price_rule")
                value = q.get("price_value")
                if value in (None, ""):
                    errors.append(f"Question '{text[:60]}': please enter a price amount.")
                    continue
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    errors.append(f"Question '{text[:60]}': the price amount must be a number.")
                    continue
                if rule == "match_within_pct":
                    caps = {"tolerance_pct": value}
                elif rule == "not_exceed":
                    caps = {"max": value}
                else:
                    errors.append(f"Question '{text[:60]}': please choose how the price should be checked.")
                    continue
                fee_field = fee_field or field_id
                criteria.append(
                    {
                        **base,
                        "verifiable": "web",
                        "check_type": "fee_match",
                        "evidence_label": f"Evidence: {text[:60]}",
                        "caps": caps,
                    }
                )
            elif kind == "exclusion_list":
                item_field_label = q.get("item_field_label")
                field_id = field_ids_by_label.get(item_field_label or "")
                if not field_id:
                    errors.append(
                        f"Question '{text[:60]}': please choose which field names the item being requested."
                    )
                    continue
                terms = [t.strip() for t in (q.get("exclusion_terms") or []) if t and t.strip()]
                if not terms:
                    errors.append(f"Question '{text[:60]}': please add at least one excluded item/term.")
                    continue
                item_name_field = item_name_field or field_id
                criteria.append(
                    {
                        **base,
                        "verifiable": "web",
                        "check_type": "exclusion_list",
                        "evidence_label": "",
                        "exclusion_list": terms,
                    }
                )
            else:
                errors.append(f"Question '{text[:60]}': please choose how the tool should check this.")
        elif checkable in ("internal", "document"):
            why_not = (q.get("why_not_checkable") or "").strip()
            if not why_not:
                errors.append(
                    f"Question '{text[:60]}': please briefly explain why this can't be checked "
                    "from the website (e.g. what record would answer it)."
                )
                continue
            criteria.append(
                {
                    **base,
                    "verifiable": checkable,
                    "check_type": "rule",
                    "evidence_label": "",
                    "explanation": why_not,
                }
            )
        else:
            errors.append(f"Question '{text[:60]}': please choose whether this can be checked from the website.")

    if not criteria:
        errors.append("Please add at least one checklist question.")

    if errors:
        return None, errors

    config_dict: dict[str, Any] = {
        "category_id": category_id,
        "display_name": display_name,
        "form_template_signature": signature_phrases,
        "fields": fields,
        "criteria": criteria,
    }
    if fee_field:
        config_dict["fee_field"] = fee_field
    if item_name_field:
        config_dict["item_name_field"] = item_name_field

    # Final structural check against the same model the loader uses — catches
    # anything the plain-language checks above didn't anticipate. Any error
    # here is a bug in this builder, not user input, so it's labeled as such.
    try:
        ChecklistConfig.model_validate(config_dict)
    except Exception as exc:  # pragma: no cover - defensive fallback
        return None, [f"Internal validation error (please report this): {exc}"]

    return config_dict, []


def wizard_from_checklist_config(cfg: ChecklistConfig) -> dict[str, Any]:
    """Reverse mapping: pre-fills the wizard when opening an existing live
    category for editing. Best-effort — a hand-authored YAML using a
    check_type/verifiable combination the wizard doesn't offer (e.g. a
    `rule` criterion with a `document` distinction, or `form_question`
    overrides) still round-trips into *a* config, just described in the
    wizard's simplified vocabulary rather than preserving every nuance.
    """
    field_label_by_id = {f.id: f.label for f in cfg.fields}

    questions = []
    for c in cfg.criteria:
        q: dict[str, Any] = {
            "text": c.question,
            "notes": c.notes,
            "group": c.group,
        }
        if c.verifiable == "web":
            q["checkable_from_website"] = "yes"
            if c.check_type == "fee_match":
                q["web_check_kind"] = "price_compare"
                q["price_field_label"] = field_label_by_id.get(cfg.fee_field or "", "")
                if "tolerance_pct" in c.caps:
                    q["price_rule"] = "match_within_pct"
                    q["price_value"] = c.caps["tolerance_pct"]
                elif "max" in c.caps:
                    q["price_rule"] = "not_exceed"
                    q["price_value"] = c.caps["max"]
            elif c.check_type == "exclusion_list":
                q["web_check_kind"] = "exclusion_list"
                q["item_field_label"] = field_label_by_id.get(cfg.item_name_field or "", "")
                q["exclusion_terms"] = list(c.exclusion_list)
            else:
                q["web_check_kind"] = "general_judgment"
        else:
            q["checkable_from_website"] = c.verifiable  # "internal" | "document"
            q["why_not_checkable"] = c.explanation
        questions.append(q)

    return {
        "category_display_name": cfg.display_name,
        "category_id": cfg.category_id,
        "signature_phrases": list(cfg.form_template_signature),
        "fields": [
            {
                "label": f.label,
                "type": _FIELD_TYPE_LABELS_REVERSE.get(f.type, "text"),
                "pii": f.pii,
            }
            for f in cfg.fields
        ],
        "questions": questions,
    }


def to_yaml_text(config_dict: dict[str, Any]) -> str:
    import yaml

    return yaml.dump(config_dict, sort_keys=False, allow_unicode=True)
