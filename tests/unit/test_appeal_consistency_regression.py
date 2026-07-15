"""Appeal consistency (PM QA on Samples 02 vs 10): an appeal must re-run the
*exact* base-category website checks, not a reworded copy that can drift.

The appeals config currently hand-mirrors community-classes' web criteria (the
YAML says so). If that copy ever drifts — a different question wording, a
different check_type or cap — the LLM would see a different prompt and the same
provider/page could legitimately produce different verdicts. This test locks
the shared web criteria byte-for-byte against the base category so any drift
fails CI immediately. (It cannot force identical *live* LLM verdicts on
ambiguous pages — that's mitigated separately by the absence-is-not-proof rule,
the targeted-evidence requirement, and the confidence re-check.)
"""

from preapproval_tool.checklist_engine.loader import get_checklist


def _web_by_id(config):
    return {c.id: c for c in config.criteria if c.verifiable == "web"}


def test_appeal_declares_the_base_category_it_reruns():
    appeal = get_checklist("appeals")
    assert appeal.appeal_of == "community-classes"


def test_appeal_web_criteria_match_the_base_category_exactly():
    appeal_web = _web_by_id(get_checklist("appeals"))
    base_web = _web_by_id(get_checklist("community-classes"))

    # Every base web criterion must be present in the appeal, identical on the
    # fields that determine how it is evaluated and prompted.
    for cid, base in base_web.items():
        assert cid in appeal_web, f"appeal is missing base web criterion '{cid}'"
        a = appeal_web[cid]
        assert a.question == base.question, f"question drift on '{cid}'"
        assert a.check_type == base.check_type, f"check_type drift on '{cid}'"
        assert a.verifiable == base.verifiable, f"verifiable drift on '{cid}'"
        assert a.caps == base.caps, f"caps drift on '{cid}'"
        assert a.exclusion_list == base.exclusion_list, f"exclusion_list drift on '{cid}'"
        assert a.form_question_text == base.form_question_text, f"form-question drift on '{cid}'"


def test_appeal_covers_all_base_web_criteria():
    appeal_web = _web_by_id(get_checklist("appeals"))
    base_web = _web_by_id(get_checklist("community-classes"))
    assert set(base_web).issubset(set(appeal_web))
