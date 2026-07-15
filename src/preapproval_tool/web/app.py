"""FastAPI reviewer app: upload -> confirm extraction -> research -> report.

This is the "web UI" surface decided in Phase 1 (§18). It is a thin layer over
the same pipeline modules used by the CLI/batch runner (scripts/run_sample.py)
— no pipeline logic lives here, only request handling, background-task
orchestration for the research step, and template rendering.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.templating import Jinja2Templates

from preapproval_tool.categorization.classifier import (
    CategoryAmbiguousError,
    classify,
)
from preapproval_tool.checklist_engine.draft_builder import (
    to_yaml_text,
    validate_wizard,
    wizard_from_checklist_config,
)
from preapproval_tool.checklist_engine.draft_store import ChecklistDraft, draft_store
from preapproval_tool.checklist_engine.loader import (
    CHECKLISTS_DIR,
    ChecklistConfigError,
    load_all_checklists,
)
from preapproval_tool.checklist_engine.models import ChecklistConfig
from preapproval_tool.evaluation.evaluator import run_evaluation
from preapproval_tool.evidence.capture_service import EvidenceCaptureService
from preapproval_tool.extraction.field_extractor import extract_fields
from preapproval_tool.extraction.pdf_text import extract_pdf_text
from preapproval_tool.llm.client import LLMError
from preapproval_tool.report.generator import (
    build_report_data,
    render_report_html,
    write_report_package,
    write_report_pdf,
)
from preapproval_tool.report.summary import generate_executive_summary
from preapproval_tool.web import export as export_mod
from preapproval_tool.web.store import ApplicationRecord, store

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("preapproval_tool.web")

app = FastAPI(title="Pre-Approval Website-Verification Tool")

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="14" fill="#0071e3"/>'
    '<path d="M18 33l10 10 18-20" fill="none" stroke="white" stroke-width="6" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(content=_FAVICON_SVG, media_type="image/svg+xml")


@app.exception_handler(LLMError)
async def llm_error_handler(request: Request, exc: LLMError) -> HTMLResponse:
    return templates.TemplateResponse(request, "error.html", {"message": str(exc)}, status_code=502)


@app.exception_handler(ChecklistConfigError)
async def checklist_error_handler(request: Request, exc: ChecklistConfigError) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "error.html", {"message": f"Checklist configuration error: {exc}"}, status_code=500
    )


def _run_research_background(app_id: str) -> None:
    """Runs in a background thread so the confirm/regenerate request can
    return immediately to a progress screen that polls real pipeline state,
    instead of blocking the HTTP request for the full research duration.
    """
    record = store.get(app_id)
    if record is None:
        return
    assert record.checklist is not None and record.extracted is not None

    record.stage = "researching"
    record.progress_error = ""

    def on_progress(message: str) -> None:
        record.progress_message = message

    try:
        capture_service = EvidenceCaptureService(record.run_dir)
        evaluation = run_evaluation(
            record.checklist, record.extracted, capture_service, on_progress=on_progress
        )
        record.reapply_review_state(evaluation.findings)

        appeal_reason = None
        if record.checklist.appeal_of:
            appeal_reason = record.extracted.value("denial_reason")

        report = build_report_data(
            record.checklist,
            record.extracted,
            evaluation,
            application_id=record.id,
            appeal_denial_reason=appeal_reason,
        )
        on_progress("Writing a plain-language summary...")
        try:
            report.executive_summary = generate_executive_summary(report)
        except Exception:  # noqa: BLE001 — summary is a nicety, never load-bearing
            report.executive_summary = None
        record.evaluation = evaluation
        record.report = report
        record.stage = "reported"
    except Exception as exc:  # noqa: BLE001 — must not crash the background thread
        logger.exception("Research failed for application %s", app_id)
        record.stage = "failed"
        record.progress_error = str(exc)


def _start_research(app_id: str) -> None:
    record = _get_record(app_id)
    record.stage = "researching"
    record.progress_message = "Starting..."
    record.progress_error = ""
    threading.Thread(target=_run_research_background, args=(app_id,), daemon=True).start()


@app.get("/", response_class=HTMLResponse)
def upload_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "upload.html", {})


def _validate_pdf_upload(filename: str | None, pdf_bytes: bytes) -> None:
    if not filename or not filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Please upload a .pdf file.")
    max_bytes = 20 * 1024 * 1024
    if len(pdf_bytes) > max_bytes:
        raise HTTPException(400, "PDF exceeds the 20MB upload limit.")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise HTTPException(400, "This file doesn't look like a valid PDF.")


@app.post("/applications")
async def create_application(file: UploadFile) -> RedirectResponse:
    pdf_bytes = await file.read()
    _validate_pdf_upload(file.filename, pdf_bytes)

    record = store.new(file.filename, pdf_bytes)

    try:
        pdf_text = extract_pdf_text(record.pdf_path)
    except Exception as exc:  # noqa: BLE001 — surface as a clean error page, not a 500 traceback
        raise HTTPException(400, f"Could not read this PDF: {exc}") from exc

    try:
        classification = classify(pdf_text.full_text)
    except CategoryAmbiguousError as exc:
        record.classification_note = (
            f"Could not confidently determine the category: {exc}. "
            f"Candidates: {', '.join(exc.candidates)}. Defaulting to the first "
            "candidate — please confirm/correct on the next screen."
        )
        category_id = exc.candidates[0]
    else:
        record.classification_note = (
            f"Category detected via {classification.method} "
            f"({classification.confidence} confidence)."
        )
        category_id = classification.category_id

    all_checklists = load_all_checklists()
    try:
        checklist = all_checklists[category_id]
    except KeyError as exc:
        raise HTTPException(500, f"No checklist config found for category '{category_id}'.") from exc

    record.checklist = checklist
    record.extracted = extract_fields(checklist, pdf_text)
    record.original_extracted_values = dict(record.extracted.values)
    record.stage = "extracted"
    return RedirectResponse(f"/applications/{record.id}/confirm", status_code=303)


@app.get("/applications/{app_id}/confirm", response_class=HTMLResponse)
def confirm_page(request: Request, app_id: str) -> HTMLResponse:
    record = _get_record(app_id)
    all_checklists = load_all_checklists()
    return templates.TemplateResponse(
        request,
        "confirm.html",
        {
            "record": record,
            "checklist": record.checklist,
            "all_categories": {cid: c.display_name for cid, c in all_checklists.items()},
        },
    )


@app.post("/applications/{app_id}/confirm")
async def confirm_application(request: Request, app_id: str) -> RedirectResponse:
    record = _get_record(app_id)
    assert record.checklist is not None and record.extracted is not None
    form = await request.form()

    category_override = str(form.get("category_id", "")).strip()
    if category_override and category_override != record.checklist.category_id:
        record.checklist = load_all_checklists()[category_override]
        record.classification_note = "Category manually corrected by reviewer."

    for field_def in record.checklist.fields:
        if field_def.id in form:
            raw = str(form[field_def.id]).strip()
            value: Any = raw or None
            if value is not None and field_def.type in ("number", "currency"):
                try:
                    value = float(raw)
                except ValueError:
                    value = None
            record.extracted.values[field_def.id] = value

    _start_research(app_id)
    return RedirectResponse(f"/applications/{app_id}/progress", status_code=303)


@app.get("/applications/{app_id}/progress", response_class=HTMLResponse)
def progress_page(request: Request, app_id: str) -> HTMLResponse:
    record = _get_record(app_id)
    return templates.TemplateResponse(request, "progress.html", {"record": record})


@app.get("/applications/{app_id}/status")
def application_status(app_id: str) -> JSONResponse:
    record = _get_record(app_id)
    return JSONResponse(
        {
            "stage": record.stage,
            "message": record.progress_message,
            "error": record.progress_error,
        }
    )


@app.post("/applications/{app_id}/regenerate")
def regenerate(app_id: str) -> RedirectResponse:
    _start_research(app_id)
    return RedirectResponse(f"/applications/{app_id}/progress", status_code=303)


def _tab_anchor(finding) -> str:
    return "internal" if finding.status == "internal" else "findings"


@app.post("/applications/{app_id}/findings/{criterion_id}/override")
async def override_finding(request: Request, app_id: str, criterion_id: str) -> RedirectResponse:
    record = _get_record(app_id)
    if not record.report:
        raise HTTPException(400, "No report to override yet.")
    form = await request.form()
    finding = _get_finding(record, criterion_id)
    is_internal = finding.status == "internal"
    status = "internal" if is_internal else str(form.get("status", "needs_review"))
    note = str(form.get("note", ""))
    document = str(form.get("document", "")).strip()
    if document:
        note = f"{note}\n\nDocument checked: {document}".strip()
    finding.apply_reviewer_override(status=status, note=note)  # type: ignore[arg-type]
    record.record_override(criterion_id, status=status, note=note)
    return RedirectResponse(f"/applications/{app_id}/report#{_tab_anchor(finding)}", status_code=303)


@app.post("/applications/{app_id}/findings/{criterion_id}/mark-reviewed")
def mark_reviewed(app_id: str, criterion_id: str) -> RedirectResponse:
    record = _get_record(app_id)
    if not record.report:
        raise HTTPException(400, "No report yet.")
    finding = _get_finding(record, criterion_id)
    finding.mark_reviewed()
    record.record_mark_reviewed(criterion_id, status=finding.status, note=finding.note)
    return RedirectResponse(f"/applications/{app_id}/report#{_tab_anchor(finding)}", status_code=303)


@app.post("/applications/{app_id}/findings/{criterion_id}/restore")
def restore_finding(app_id: str, criterion_id: str) -> RedirectResponse:
    record = _get_record(app_id)
    if not record.report:
        raise HTTPException(400, "No report yet.")
    finding = _get_finding(record, criterion_id)
    finding.restore_system_result()
    record.clear_override(criterion_id)
    return RedirectResponse(f"/applications/{app_id}/report#{_tab_anchor(finding)}", status_code=303)


@app.get("/applications/{app_id}/report", response_class=HTMLResponse)
def report_page(request: Request, app_id: str) -> HTMLResponse:
    record = _get_record(app_id)
    if record.stage == "failed":
        return templates.TemplateResponse(
            request, "error.html", {"message": f"Research failed: {record.progress_error}"}
        )
    if record.stage != "reported" or not record.report:
        return RedirectResponse(f"/applications/{app_id}/progress")
    html = render_report_html(record.report, interactive=True, app_id=app_id)
    return HTMLResponse(html)


@app.get("/applications/{app_id}/evidence/{filename}")
def evidence_file(app_id: str, filename: str) -> FileResponse:
    record = _get_record(app_id)
    path = record.run_dir / "evidence" / filename
    if not path.exists() or path.resolve().parent != (record.run_dir / "evidence").resolve():
        raise HTTPException(404)
    return FileResponse(path)


@app.get("/applications/{app_id}/export/report.html")
def export_report_html(app_id: str) -> FileResponse:
    record = _get_record(app_id)
    if not record.report:
        raise HTTPException(400, "No report to export yet.")
    path = write_report_package(record.report, record.run_dir)
    return FileResponse(path, filename=f"report-{app_id}.html", media_type="text/html")


@app.get("/applications/{app_id}/export/report.pdf")
def export_report_pdf(app_id: str) -> FileResponse:
    record = _get_record(app_id)
    if not record.report:
        raise HTTPException(400, "No report to export yet.")
    write_report_package(record.report, record.run_dir)  # ensures evidence/ is on disk
    path = write_report_pdf(record.report, record.run_dir)
    return FileResponse(path, filename=f"report-{app_id}.pdf", media_type="application/pdf")


@app.get("/applications/{app_id}/export/report.json")
def export_report_json(app_id: str) -> JSONResponse:
    record = _get_record(app_id)
    if not record.report:
        raise HTTPException(400, "No report to export yet.")
    return JSONResponse(export_mod.build_report_json(record.report))


@app.get("/applications/{app_id}/export/package.zip")
def export_package(app_id: str) -> StreamingResponse:
    record = _get_record(app_id)
    if not record.report:
        raise HTTPException(400, "No report to export yet.")
    write_report_package(record.report, record.run_dir)
    data = export_mod.build_package_zip(record)
    return StreamingResponse(
        iter([data]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="package-{app_id}.zip"'},
    )


# ============ Manage Checklists (non-technical checklist authoring) ============
#
# A non-technical user can add/edit a checklist category through a
# plain-language wizard instead of hand-authoring YAML. Per the locked
# product decision: a saved wizard is always a *draft* — it never touches
# config/checklists/*.yaml (and is therefore never used by real reviewer
# traffic) until an engineer/lead reviewer explicitly clicks "Publish."


@app.get("/manage-checklists", response_class=HTMLResponse)
def manage_checklists_page(request: Request) -> HTMLResponse:
    live = load_all_checklists()
    drafts = draft_store.list_all()
    return templates.TemplateResponse(
        request,
        "manage_checklists.html",
        {"live_categories": live, "drafts": drafts},
    )


@app.get("/manage-checklists/new", response_class=HTMLResponse)
def new_checklist_wizard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "checklist_wizard.html",
        {"draft_id": None, "source_category_id": None, "initial_wizard_json": "null"},
    )


@app.get("/manage-checklists/edit/{category_id}", response_class=HTMLResponse)
def edit_live_checklist_wizard(request: Request, category_id: str) -> HTMLResponse:
    live = load_all_checklists()
    if category_id not in live:
        raise HTTPException(404, f"Unknown category '{category_id}'.")
    wizard = wizard_from_checklist_config(live[category_id])
    return templates.TemplateResponse(
        request,
        "checklist_wizard.html",
        {
            "draft_id": None,
            "source_category_id": category_id,
            "initial_wizard_json": json.dumps(wizard),
        },
    )


def _get_draft(draft_id: str) -> ChecklistDraft:
    draft = draft_store.get(draft_id)
    if not draft:
        raise HTTPException(404, "Draft not found.")
    return draft


@app.get("/manage-checklists/drafts/{draft_id}/wizard", response_class=HTMLResponse)
def edit_draft_wizard(request: Request, draft_id: str) -> HTMLResponse:
    draft = _get_draft(draft_id)
    return templates.TemplateResponse(
        request,
        "checklist_wizard.html",
        {
            "draft_id": draft.id,
            "source_category_id": draft.source_category_id,
            "initial_wizard_json": json.dumps(draft.wizard),
        },
    )


@app.get("/manage-checklists/drafts/{draft_id}", response_class=HTMLResponse)
def draft_review_page(request: Request, draft_id: str) -> HTMLResponse:
    draft = _get_draft(draft_id)
    config_dict, errors = validate_wizard(draft.wizard)
    yaml_text = to_yaml_text(config_dict) if config_dict else None
    return templates.TemplateResponse(
        request,
        "checklist_draft_review.html",
        {
            "draft": draft,
            "errors": errors,
            "config_dict": config_dict,
            "yaml_text": yaml_text,
        },
    )


@app.post("/manage-checklists/drafts")
async def create_draft(request: Request) -> JSONResponse:
    body = await request.json()
    wizard = body.get("wizard") or {}
    source_category_id = body.get("source_category_id")
    draft = draft_store.new(wizard, source_category_id=source_category_id)
    return JSONResponse({"draft_id": draft.id})


@app.post("/manage-checklists/drafts/{draft_id}")
async def update_draft(request: Request, draft_id: str) -> JSONResponse:
    draft = _get_draft(draft_id)
    body = await request.json()
    draft.wizard = body.get("wizard") or {}
    draft_store.save(draft)
    return JSONResponse({"ok": True})


@app.post("/manage-checklists/drafts/{draft_id}/test")
async def test_draft(draft_id: str, file: UploadFile) -> JSONResponse:
    draft = _get_draft(draft_id)
    config_dict, errors = validate_wizard(draft.wizard)
    if errors:
        return JSONResponse({"errors": errors}, status_code=400)
    assert config_dict is not None
    checklist = ChecklistConfig.model_validate(config_dict)

    pdf_bytes = await file.read()
    _validate_pdf_upload(file.filename, pdf_bytes)

    tmp_dir = Path("output/runs") / f"_draft_test_{draft_id}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = tmp_dir / "test.pdf"
    pdf_path.write_bytes(pdf_bytes)

    try:
        pdf_text = extract_pdf_text(pdf_path)
        extracted = extract_fields(checklist, pdf_text)
        capture_service = EvidenceCaptureService(tmp_dir)
        evaluation = run_evaluation(checklist, extracted, capture_service)
    except Exception as exc:  # noqa: BLE001 — show the tester a clean message, not a 500
        return JSONResponse({"errors": [f"Test run failed: {exc}"]}, status_code=400)

    summary = {
        "extracted_fields": extracted.values,
        "low_confidence_fields": extracted.low_confidence_fields,
        "findings": [
            {"question": f.question, "status": f.status, "note": f.note}
            for f in evaluation.findings
        ],
        "fetch_error": evaluation.fetch_error,
    }
    draft.last_test_summary = summary
    draft_store.save(draft)
    return JSONResponse(summary)


@app.post("/manage-checklists/drafts/{draft_id}/publish")
def publish_draft(draft_id: str) -> JSONResponse:
    draft = _get_draft(draft_id)
    config_dict, errors = validate_wizard(draft.wizard)
    if errors:
        return JSONResponse({"errors": errors}, status_code=400)
    assert config_dict is not None

    new_category_id = config_dict["category_id"]
    live = load_all_checklists()
    if new_category_id in live and (
        draft.source_category_id is None or draft.source_category_id != new_category_id
    ):
        return JSONResponse(
            {"errors": [f"A category '{new_category_id}' already exists — choose a different name."]},
            status_code=400,
        )

    CHECKLISTS_DIR.mkdir(parents=True, exist_ok=True)
    new_path = CHECKLISTS_DIR / f"{new_category_id}.yaml"
    new_path.write_text(to_yaml_text(config_dict))

    if draft.source_category_id and draft.source_category_id != new_category_id:
        old_path = CHECKLISTS_DIR / f"{draft.source_category_id}.yaml"
        if old_path.exists():
            old_path.unlink()

    load_all_checklists.cache_clear()
    draft_store.delete(draft_id)
    return JSONResponse({"category_id": new_category_id})


@app.post("/manage-checklists/drafts/{draft_id}/discard")
def discard_draft(draft_id: str) -> RedirectResponse:
    draft_store.delete(draft_id)
    return RedirectResponse("/manage-checklists", status_code=303)


def _get_record(app_id: str) -> ApplicationRecord:
    record = store.get(app_id)
    if not record:
        raise HTTPException(404, "Application not found.")
    return record


def _get_finding(record: ApplicationRecord, criterion_id: str):
    assert record.report is not None
    finding = next((f for f in record.report.findings if f.criterion_id == criterion_id), None)
    if not finding:
        raise HTTPException(404, f"No finding '{criterion_id}' on this report.")
    return finding
