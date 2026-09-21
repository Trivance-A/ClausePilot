import uuid

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
