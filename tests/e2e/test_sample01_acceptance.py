"""Full live acceptance test for Sample 01, covering the 15-step flow from
the Phase 2.A review: upload -> extract -> confirm -> research -> report ->
navigate sections -> view evidence -> add note -> override -> refresh
persistence -> regenerate -> distinct system/reviewer results -> export ->
evidence manifest.

Opt-in only (`pytest -m e2e`): it starts a real uvicorn server, makes real
OpenAI + Firecrawl API calls, and costs a small amount of API usage. Requires
a real .env with OPENAI_API_KEY and FIRECRAWL_API_KEY.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import zipfile
from contextlib import closing
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_01 = REPO_ROOT / "samples" / "Sample-01---Community-Class-GallopNYC.pdf"


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server():
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "preapproval_tool.web.app:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=REPO_ROOT,
    )
    base_url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                break
        except OSError:
            time.sleep(0.5)
    else:
        proc.terminate()
        raise RuntimeError("Server did not start in time")
    yield base_url
    proc.terminate()
    proc.wait(timeout=10)


def test_sample01_full_acceptance_flow(live_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        console_errors = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)

        # 1. Upload PDF
        page.goto(live_server)
        page.set_input_files("#file-input", str(SAMPLE_01))
        page.click("#submit-btn")

        # 2/3. Extract + confirm/edit fields
        page.wait_for_url("**/confirm", timeout=30000)
        assert page.locator("#field-participant_name").input_value() == "Aaron M."

        # 4. Confirm category (leave as detected) + 5. Research website
        page.click("#confirm-submit", timeout=60000)
        page.wait_for_url("**/progress", timeout=30000)
        page.wait_for_url("**/report", timeout=180000)
        page.wait_for_load_state("networkidle")
        app_url = page.url
        app_id = app_url.rstrip("/").split("/")[-2]

        # 6. Generate report (implicit) — 7. Navigate report sections
        for tab in ["tab-findings", "tab-evidence", "tab-internal", "tab-export", "tab-overview"]:
            page.click(f"#{tab}")
            page.wait_for_timeout(150)

        # 8. View evidence
        page.click("#tab-evidence")
        page.wait_for_timeout(200)
        assert page.locator(".evidence-card").count() > 0
        page.locator(".evidence-card .thumb").first.click()
        page.wait_for_timeout(200)
        assert page.eval_on_selector("#lightbox", "el => el.open") is True
        page.keyboard.press("Escape")

        # 9. Add reviewer note + 10. Override one status
        page.click("#tab-findings")
        page.wait_for_timeout(200)
        card = page.locator(".finding-card").first
        card.locator("> summary").click()
        card.locator(".edit-disclosure > summary").click()
        card.locator("select[name=status]").select_option("found")
        card.locator("textarea[name=note]").fill("E2E test override note.")
        card.locator(".edit-form button[type=submit]").click()
        page.wait_for_load_state("networkidle")

        # 11. Refresh and confirm persistence
        page.reload()
        page.wait_for_load_state("networkidle")
        page.click("#tab-findings")
        page.wait_for_timeout(200)
        assert page.locator(".overridden-tag").count() >= 1
        first_findings_card = page.locator(".finding-card").first
        first_findings_card.locator("> summary").click()
        assert "E2E test override note." in first_findings_card.inner_text()

        # 12. Regenerate report
        page.once("dialog", lambda d: d.accept())
        page.get_by_role("button", name="Regenerate report").click(timeout=180000)
        page.wait_for_url("**/progress", timeout=30000)
        page.wait_for_url("**/report", timeout=180000)
        page.wait_for_load_state("networkidle")

        # 13. Confirm original and reviewer results remain distinct
        page.click("#tab-findings")
        page.wait_for_timeout(200)
        first_card = page.locator(".finding-card").first
        first_card.locator("> summary").click()
        # .overridden-tag is styled text-transform: uppercase, so Playwright's
        # rendered inner_text() reflects that — compare case-insensitively.
        first_card_text = first_card.inner_text().lower()
        assert "reviewer decision" in first_card_text
        assert "system originally said" in first_card_text

        # 14. Export report package + 15. Validate exported evidence manifest
        resp = page.request.get(f"{live_server}/applications/{app_id}/export/package.zip")
        assert resp.status == 200
        zip_bytes = resp.body()
        zip_path = REPO_ROOT / "output" / "runs" / f"_e2e_test_{app_id}.zip"
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        zip_path.write_bytes(zip_bytes)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            assert "report.html" in names
            assert "report.json" in names
            assert any(n.startswith("evidence/") for n in names)
            report_json = json.loads(zf.read("report.json"))
            assert report_json["validation_issues"] == []
        zip_path.unlink()

        assert console_errors == [], f"Unexpected console errors: {console_errors}"
        browser.close()
