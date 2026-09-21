"""4주차 시점: 엔드포인트는 스텁 상태(501)이므로 '라우트가 올바르게 존재하는지'만 검증한다.
6주차에 실제 로직이 채워지면 이 테스트들을 실제 동작(200/202 + 응답 스키마) 검증으로 교체해야 한다.
"""

import uuid


def test_upload_document_route_exists(client):
    response = client.post("/documents", files={"file": ("test.pdf", b"%PDF-1.4", "application/pdf")})

    assert response.status_code == 501


def test_get_document_status_route_exists(client):
    response = client.get(f"/documents/{uuid.uuid4()}/status")

    assert response.status_code == 501


def test_get_document_result_route_exists(client):
    response = client.get(f"/documents/{uuid.uuid4()}/result")

    assert response.status_code == 501


def test_get_document_ocr_blocks_route_exists(client):
    response = client.get(f"/documents/{uuid.uuid4()}/ocr-blocks")

    assert response.status_code == 501


def test_get_document_status_rejects_invalid_uuid(client):
    response = client.get("/documents/not-a-uuid/status")

    assert response.status_code == 422
