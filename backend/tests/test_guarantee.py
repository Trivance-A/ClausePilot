import uuid

from tests.helpers import upload_and_wait_document


def test_create_guarantee_application(client, admin_headers):
    doc_id = upload_and_wait_document(client, admin_headers)
    r = client.post("/api/v1/guarantee-applications", headers=admin_headers, json={"document_id": doc_id, "guarantee_type": "contract"})
    assert r.status_code == 201
    body = r.json()
    assert body["form_values"]["contract_amount"] == 350000000
    assert body["form_values"]["creditor_biz_no"] == "123-45-67890"
    assert body["required_fields"] == [
        "contract_name", "contract_amount", "guarantee_amount", "contract_date",
        "performance_due_date", "guarantee_period", "creditor_name", "creditor_biz_no",
    ]
    assert body["viewer_url"] == f"/documents/{doc_id}/viewer?field=contract_amount"


def test_create_guarantee_application_without_extraction_is_409(client, admin_headers):
    r = client.post("/api/v1/guarantee-applications", headers=admin_headers, json={"document_id": str(uuid.uuid4()), "guarantee_type": "bid"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "INVALID_STATE"


def test_patch_guarantee_application_submits(client, admin_headers):
    doc_id = upload_and_wait_document(client, admin_headers)
    created = client.post("/api/v1/guarantee-applications", headers=admin_headers, json={"document_id": doc_id, "guarantee_type": "bid"}).json()

    r = client.patch(
        f"/api/v1/guarantee-applications/{created['id']}",
        headers=admin_headers,
        json={"form_values": created["form_values"], "status": "SUBMITTED"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "SUBMITTED"
    # bid 유형은 guarantee_period/performance_due_date가 필수가 아니다
    assert "guarantee_period" not in r.json()["required_fields"]
