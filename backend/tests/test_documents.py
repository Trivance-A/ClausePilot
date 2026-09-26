import uuid

from tests.doc_fixtures import docx_bytes, xlsx_bytes
from tests.helpers import upload_and_wait_document
from tests.pdf_fixtures import contract_pdf_bytes


def test_upload_and_pipeline_completes(client, admin_headers):
    doc_id = upload_and_wait_document(client, admin_headers)
    r = client.get(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "DONE"
    assert body["page_count"] == 1
    assert body["extraction"] is not None


def test_list_documents_filters_by_status(client, admin_headers):
    doc_id = upload_and_wait_document(client, admin_headers)
    r = client.get("/api/v1/documents", headers=admin_headers, params={"status": "DONE", "size": 50})
    assert r.status_code == 200
    ids = [item["id"] for item in r.json()["items"]]
    assert doc_id in ids


def test_document_lines_and_pdf(client, admin_headers):
    doc_id = upload_and_wait_document(client, admin_headers)
    r = client.get(f"/api/v1/documents/{doc_id}/lines", headers=admin_headers, params={"page": 1})
    assert r.status_code == 200
    assert len(r.json()["lines"]) > 0

    r = client.get(f"/api/v1/documents/{doc_id}/pdf", headers=admin_headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"


def test_reprocess_from_risk(client, admin_headers):
    doc_id = upload_and_wait_document(client, admin_headers)
    r = client.post(f"/api/v1/documents/{doc_id}/reprocess", headers=admin_headers, json={"from_step": "risk"})
    assert r.status_code == 202
    assert r.json()["job_id"]


def test_delete_document_cascades(client, admin_headers):
    doc_id = upload_and_wait_document(client, admin_headers)
    r = client.delete(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    assert r.status_code == 204
    assert client.get(f"/api/v1/documents/{doc_id}", headers=admin_headers).status_code == 404
    assert client.get(f"/api/v1/documents/{doc_id}/extractions", headers=admin_headers).status_code == 404


def test_get_unknown_document_returns_error_envelope(client, admin_headers):
    r = client.get(f"/api/v1/documents/{uuid.uuid4()}", headers=admin_headers)
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "NOT_FOUND", "message": "문서를 찾을 수 없습니다", "detail": None}}


def test_upload_requires_auth(client):
    r = client.post("/api/v1/documents", files={"files": ("a.pdf", contract_pdf_bytes(), "application/pdf")}, data={"ocr_engine": "auto", "skip_risk": "false"})
    assert r.status_code == 401


def test_page_image_endpoint(client, admin_headers):
    doc_id = upload_and_wait_document(client, admin_headers)
    r = client.get(f"/api/v1/documents/{doc_id}/pages/1/image", headers=admin_headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"  # PNG 매직 넘버


def test_page_image_out_of_range_is_404(client, admin_headers):
    doc_id = upload_and_wait_document(client, admin_headers)
    r = client.get(f"/api/v1/documents/{doc_id}/pages/99/image", headers=admin_headers)
    assert r.status_code == 404


def test_upload_docx_extracts_fields(client, admin_headers):
    doc_id = upload_and_wait_document(client, admin_headers, filename="test.docx", content=docx_bytes(), content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    fields = {f["field_code"]: f for f in client.get(f"/api/v1/documents/{doc_id}/extractions", headers=admin_headers).json()["fields"]}
    assert fields["contract_amount"]["normalized_value"] == {"amount": 220000000}
    assert fields["contract_date"]["normalized_value"] == {"date": "2026-01-15"}


def test_upload_xlsx_extracts_fields(client, admin_headers):
    doc_id = upload_and_wait_document(client, admin_headers, filename="test.xlsx", content=xlsx_bytes(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    fields = {f["field_code"]: f for f in client.get(f"/api/v1/documents/{doc_id}/extractions", headers=admin_headers).json()["fields"]}
    assert fields["contract_amount"]["normalized_value"] == {"amount": 99000000}


def test_upload_real_hwp_extracts_text(client, admin_headers):
    """프로젝트 루트의 실제 RFP .hwp 파일로 hwp5txt 연동을 검증한다."""
    from pathlib import Path

    hwp_path = Path(__file__).resolve().parents[2] / "제안요청서_AI보증신청 및 챗봇 시스템 개발.hwp"
    if not hwp_path.exists():
        import pytest

        pytest.skip("샘플 hwp 파일이 없는 환경(레포 루트 밖)")
    doc_id = upload_and_wait_document(client, admin_headers, filename="rfp.hwp", content=hwp_path.read_bytes(), content_type="application/x-hwp")
    r = client.get(f"/api/v1/documents/{doc_id}/lines", headers=admin_headers, params={"page": 1})
    assert r.status_code == 200
    assert len(r.json()["lines"]) > 0


def test_upload_unsupported_format_fails(client, admin_headers):
    doc_id = upload_and_wait_document(client, admin_headers, filename="test.txt", content=b"plain text", content_type="text/plain", expect_status="FAILED")
    r = client.get(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    assert r.json()["status"] == "FAILED"
