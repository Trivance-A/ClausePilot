import time

from fastapi.testclient import TestClient

from tests.pdf_fixtures import contract_pdf_bytes, regulation_pdf_bytes

TERMINAL_DOCUMENT_STATUSES = {"DONE", "FAILED"}
TERMINAL_REGULATION_STATUSES = {"INDEXED", "FAILED"}


def wait_for(fn, terminal: set[str], timeout: float = 10.0) -> str:
    deadline = time.monotonic() + timeout
    status = None
    while time.monotonic() < deadline:
        status = fn()
        if status in terminal:
            return status
        time.sleep(0.1)
    raise TimeoutError(f"timed out waiting for terminal status, last={status}")


def upload_and_wait_document(client: TestClient, headers: dict) -> str:
    r = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"files": ("test.pdf", contract_pdf_bytes(), "application/pdf")},
        data={"ocr_engine": "auto", "skip_risk": "false"},
    )
    assert r.status_code == 202, r.text
    doc_id = r.json()["items"][0]["document_id"]

    def _status() -> str:
        return client.get(f"/api/v1/documents/{doc_id}/status", headers=headers).json()["status"]

    status = wait_for(_status, TERMINAL_DOCUMENT_STATUSES)
    assert status == "DONE", f"document pipeline failed: {client.get(f'/api/v1/documents/{doc_id}', headers=headers).json()}"
    return doc_id


def upload_and_wait_regulation(client: TestClient, headers: dict, title: str = "테스트 규정") -> str:
    r = client.post(
        "/api/v1/regulations",
        headers=headers,
        files={"file": ("reg.pdf", regulation_pdf_bytes(), "application/pdf")},
        data={"title": title, "doc_type": "규정"},
    )
    assert r.status_code == 202, r.text
    reg_id = r.json()["regulation_id"]

    def _status() -> str:
        return client.get(f"/api/v1/regulations/{reg_id}", headers=headers).json()["status"]

    status = wait_for(_status, TERMINAL_REGULATION_STATUSES)
    assert status == "INDEXED", f"regulation pipeline failed: {client.get(f'/api/v1/regulations/{reg_id}', headers=headers).json()}"
    return reg_id
