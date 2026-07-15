"""Upload-boundary validation — none of these need real API keys since they
fail before the extraction/LLM pipeline is ever reached.
"""

import io

from fastapi.testclient import TestClient

from preapproval_tool.web.app import app

client = TestClient(app)


def test_rejects_non_pdf_extension():
    resp = client.post(
        "/applications", files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")}
    )
    assert resp.status_code == 400


def test_rejects_file_renamed_to_pdf_but_not_actually_a_pdf():
    resp = client.post(
        "/applications",
        files={"file": ("fake.pdf", io.BytesIO(b"this is not a pdf, just text"), "application/pdf")},
    )
    assert resp.status_code == 400
    assert "doesn't look like a valid pdf" in resp.text.lower()


def test_rejects_empty_pdf():
    resp = client.post(
        "/applications", files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")}
    )
    assert resp.status_code == 400


def test_rejects_oversized_pdf():
    oversized = b"%PDF-1.4\n" + b"0" * (21 * 1024 * 1024)
    resp = client.post(
        "/applications", files={"file": ("big.pdf", io.BytesIO(oversized), "application/pdf")}
    )
    assert resp.status_code == 400
    assert "20mb" in resp.text.lower()


def test_corrupted_pdf_header_but_truncated_body_is_handled_gracefully():
    """Passes the magic-byte check but pdfplumber can't actually parse it —
    must surface a clean 400, not a raw 500 traceback.
    """
    resp = client.post(
        "/applications",
        files={"file": ("corrupt.pdf", io.BytesIO(b"%PDF-1.4\ncorrupted garbage not a real pdf"), "application/pdf")},
    )
    assert resp.status_code == 400
