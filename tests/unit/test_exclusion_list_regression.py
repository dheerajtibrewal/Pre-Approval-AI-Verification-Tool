"""Fixture-locked regression coverage for the two adversarial samples the
brief calls out by name (Sample 07's laptop, Sample 08's weighted blanket).
These load the REAL, committed config/checklists/*.yaml files — not a copy
— so a future edit to hri.yaml/otps.yaml or exclusion_list.py that breaks
either case fails CI immediately, instead of only being caught by someone
manually re-running the live sample.
"""

from __future__ import annotations

from preapproval_tool.checklist_engine.loader import get_checklist
from preapproval_tool.evaluation.exclusion_list import evaluate_exclusion_list


def test_sample_07_laptop_hits_the_hri_computer_hardware_exclusion():
    hri = get_checklist("hri")
    criterion = hri.criterion("exclusion_list")
    assert criterion is not None

    result = evaluate_exclusion_list(criterion, item_name="Laptop computer")

    assert result["status"] == "not_found"
    assert "Computer Hardware" in result["note"]


def test_sample_08_weighted_blanket_clears_the_otps_exclusion_list():
    otps = get_checklist("otps")
    criterion = otps.criterion("exclusion_list")
    assert criterion is not None

    result = evaluate_exclusion_list(criterion, item_name="Weighted Blanket")

    assert result["status"] == "found"


def test_hri_and_otps_exclusion_lists_are_not_cross_wired():
    """A laptop is excluded under HRI's list (Computer Hardware) but must not
    be flagged under OTPS's list, which doesn't mention computers at all —
    guards against a future edit accidentally merging or sharing the two
    categories' exclusion terms.
    """
    hri = get_checklist("hri")
    otps = get_checklist("otps")

    hri_result = evaluate_exclusion_list(hri.criterion("exclusion_list"), item_name="Laptop computer")
    otps_result = evaluate_exclusion_list(otps.criterion("exclusion_list"), item_name="Laptop computer")

    assert hri_result["status"] == "not_found"
    assert otps_result["status"] == "found"


def test_otps_cable_tv_hits_its_own_exclusion_list():
    otps = get_checklist("otps")
    criterion = otps.criterion("exclusion_list")

    result = evaluate_exclusion_list(criterion, item_name="Cable TV subscription")

    assert result["status"] == "not_found"
