"""Integration test for the non-technical "Manage Checklists" web flow:
create a draft, review it, publish it, and confirm it's picked up as a live
category without a server restart (the lru_cache on load_all_checklists is
cleared on publish). Isolated from the real config/checklists/ and
data/checklist_drafts/ directories via monkeypatching, since publishing is a
real filesystem write.

No LLM/network calls here — the "test against a sample PDF" endpoint is
intentionally not exercised (that's covered, at real cost, by the e2e suite).
"""

from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

import preapproval_tool.checklist_engine.loader as loader_mod
import preapproval_tool.web.app as app_mod
from preapproval_tool.checklist_engine.draft_store import DraftStore


@pytest.fixture
def isolated_client(tmp_path, monkeypatch):
    tmp_checklists = tmp_path / "checklists"
    tmp_checklists.mkdir()
    shutil.copy(loader_mod.CHECKLISTS_DIR / "community-classes.yaml", tmp_checklists)

    tmp_drafts = tmp_path / "drafts"

    monkeypatch.setattr(loader_mod, "CHECKLISTS_DIR", tmp_checklists)
    monkeypatch.setattr(app_mod, "CHECKLISTS_DIR", tmp_checklists)
    monkeypatch.setattr(app_mod, "draft_store", DraftStore(base_dir=tmp_drafts))
    loader_mod.load_all_checklists.cache_clear()

    yield TestClient(app_mod.app)

    loader_mod.load_all_checklists.cache_clear()


def _wizard_payload() -> dict:
    return {
        "category_display_name": "Home Modifications",
        "category_id": "",
        "signature_phrases": ["Home Modification Pre-approval Form"],
        "fields": [
            {"label": "Item Requested", "type": "text", "pii": False},
        ],
        "questions": [
            {
                "text": "Does the linked page show the item with a visible price?",
                "checkable_from_website": "yes",
                "web_check_kind": "general_judgment",
            },
            {
                "text": "Is this approved in the budget?",
                "checkable_from_website": "internal",
                "why_not_checkable": "Requires the approved budget record.",
                "group": "Budget and funding",
            },
        ],
    }


def test_manage_checklists_list_shows_live_category(isolated_client):
    resp = isolated_client.get("/manage-checklists")
    assert resp.status_code == 200
    assert "Community Class" in resp.text


def test_create_draft_and_review_it(isolated_client):
    resp = isolated_client.post("/manage-checklists/drafts", json={"wizard": _wizard_payload()})
    assert resp.status_code == 200
    draft_id = resp.json()["draft_id"]

    review = isolated_client.get(f"/manage-checklists/drafts/{draft_id}")
    assert review.status_code == 200
    assert "Home Modifications" in review.text
    assert "can't be published yet" not in review.text


def test_incomplete_draft_shows_plain_language_errors_and_blocks_publish(isolated_client):
    wizard = _wizard_payload()
    wizard["category_display_name"] = ""
    resp = isolated_client.post("/manage-checklists/drafts", json={"wizard": wizard})
    draft_id = resp.json()["draft_id"]

    review = isolated_client.get(f"/manage-checklists/drafts/{draft_id}")
    assert "can't be published yet" in review.text

    publish = isolated_client.post(f"/manage-checklists/drafts/{draft_id}/publish")
    assert publish.status_code == 400
    assert publish.json()["errors"]


def test_publish_writes_yaml_and_is_immediately_live(isolated_client, tmp_path):
    resp = isolated_client.post("/manage-checklists/drafts", json={"wizard": _wizard_payload()})
    draft_id = resp.json()["draft_id"]

    publish = isolated_client.post(f"/manage-checklists/drafts/{draft_id}/publish")
    assert publish.status_code == 200
    assert publish.json()["category_id"] == "home-modifications"

    assert (loader_mod.CHECKLISTS_DIR / "home-modifications.yaml").exists()

    live = isolated_client.get("/manage-checklists")
    assert "Home Modifications" in live.text
    # Published draft should no longer appear as a pending draft.
    assert isolated_client.get(f"/manage-checklists/drafts/{draft_id}").status_code == 404


def test_publish_rejects_colliding_category_id(isolated_client):
    wizard = _wizard_payload()
    wizard["category_display_name"] = "Community Class"
    wizard["category_id"] = "community-classes"
    resp = isolated_client.post("/manage-checklists/drafts", json={"wizard": wizard})
    draft_id = resp.json()["draft_id"]

    publish = isolated_client.post(f"/manage-checklists/drafts/{draft_id}/publish")
    assert publish.status_code == 400
    assert "already exists" in publish.json()["errors"][0]


def test_editing_existing_category_can_overwrite_itself(isolated_client):
    from preapproval_tool.checklist_engine.draft_builder import wizard_from_checklist_config

    live = loader_mod.load_all_checklists()
    wizard = wizard_from_checklist_config(live["community-classes"])
    resp = isolated_client.post(
        "/manage-checklists/drafts",
        json={"wizard": wizard, "source_category_id": "community-classes"},
    )
    draft_id = resp.json()["draft_id"]

    publish = isolated_client.post(f"/manage-checklists/drafts/{draft_id}/publish")
    assert publish.status_code == 200
    assert publish.json()["category_id"] == "community-classes"


def test_discard_removes_draft(isolated_client):
    resp = isolated_client.post("/manage-checklists/drafts", json={"wizard": _wizard_payload()})
    draft_id = resp.json()["draft_id"]

    discard = isolated_client.post(f"/manage-checklists/drafts/{draft_id}/discard")
    assert discard.status_code in (200, 303)
    assert isolated_client.get(f"/manage-checklists/drafts/{draft_id}").status_code == 404
