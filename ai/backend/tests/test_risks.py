from tests.helpers import upload_and_wait_document


def test_risks_detected_from_contract_clauses(client, admin_headers):
    doc_id = upload_and_wait_document(client, admin_headers)
    r = client.get(f"/api/v1/documents/{doc_id}/risks", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    categories = {item["category"] for item in body["items"]}
    assert "penalty" in categories  # 지체상금 3/1000 조항
    assert "toxic" in categories  # 일방적 해지 조항
    assert body["summary"]["HIGH"] >= 1


def test_patch_risk_status_updates_summary(client, admin_headers):
    doc_id = upload_and_wait_document(client, admin_headers)
    risks = client.get(f"/api/v1/documents/{doc_id}/risks", headers=admin_headers).json()["items"]
    target = risks[0]

    r = client.patch(f"/api/v1/risks/{target['id']}", headers=admin_headers, json={"status": "DISMISSED", "note": "오탐"})
    assert r.status_code == 200
    assert r.json()["status"] == "DISMISSED"
    assert r.json()["note"] == "오탐"

    summary = client.get(f"/api/v1/documents/{doc_id}/risks", headers=admin_headers).json()["summary"]
    assert sum(summary.values()) == len(risks) - 1


def test_rerun_risks(client, admin_headers):
    doc_id = upload_and_wait_document(client, admin_headers)
    r = client.post(f"/api/v1/documents/{doc_id}/risks/rerun", headers=admin_headers)
    assert r.status_code == 202
    assert r.json()["job_id"]
