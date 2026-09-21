"""4주차 시점: 엔드포인트는 스텁 상태(501)이므로 '라우트가 올바르게 존재하는지'만 검증한다.
6주차에 실제 로직이 채워지면 이 테스트들을 실제 동작(200/202 + 응답 스키마) 검증으로 교체해야 한다.
"""

import uuid

BASE = "/api/v1/documents"


def test_list_documents_route_exists(client):
    response = client.get(BASE, params={"q": "계약", "status": "OCR,EXTRACTING", "page": 1, "size": 20})

    assert response.status_code == 501


def test_upload_documents_route_exists(client):
    response = client.post(
        BASE,
        files=[("files", ("test.pdf", b"%PDF-1.4", "application/pdf"))],
        data={"ocr_engine": "auto", "skip_risk": "false"},
    )

    assert response.status_code == 501


def test_get_document_status_route_exists(client):
    response = client.get(f"{BASE}/{uuid.uuid4()}/status")

    assert response.status_code == 501


def test_get_document_pdf_route_exists(client):
    response = client.get(f"{BASE}/{uuid.uuid4()}/pdf")

    assert response.status_code == 501


def test_export_document_pdf_route_exists(client):
    response = client.get(f"{BASE}/{uuid.uuid4()}/export/pdf")

    assert response.status_code == 501


def test_get_document_lines_route_exists(client):
    response = client.get(f"{BASE}/{uuid.uuid4()}/lines", params={"page": 1})

    assert response.status_code == 501


def test_get_document_lines_requires_page(client):
    response = client.get(f"{BASE}/{uuid.uuid4()}/lines")

    assert response.status_code == 422


def test_get_document_route_exists(client):
    response = client.get(f"{BASE}/{uuid.uuid4()}")

    assert response.status_code == 501


def test_reprocess_document_route_exists(client):
    response = client.post(f"{BASE}/{uuid.uuid4()}/reprocess", json={"from_step": "ocr"})

    assert response.status_code == 501


def test_delete_document_route_exists(client):
    response = client.delete(f"{BASE}/{uuid.uuid4()}")

    assert response.status_code == 501


def test_get_document_status_rejects_invalid_uuid(client):
    response = client.get(f"{BASE}/not-a-uuid/status")

    assert response.status_code == 422
