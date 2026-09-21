from tests.helpers import upload_and_wait_document


def test_extraction_fields_parsed_correctly(client, admin_headers):
    doc_id = upload_and_wait_document(client, admin_headers)
    r = client.get(f"/api/v1/documents/{doc_id}/extractions", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "AUTO"
    fields = {f["field_code"]: f for f in body["fields"]}
    assert set(fields) == {
        "contract_name", "contract_amount", "guarantee_amount", "contract_date",
        "performance_due_date", "guarantee_period", "creditor_name", "creditor_biz_no",
    }
    assert fields["contract_amount"]["normalized_value"] == {"amount": 350000000}
    assert fields["guarantee_amount"]["normalized_value"] == {"amount": 35000000}
    assert fields["contract_date"]["normalized_value"] == {"date": "2026-03-05"}
    assert fields["creditor_biz_no"]["normalized_value"] == {"text": "123-45-67890"}
    assert body["color_map"]["contract_amount"] == "#4FC3F7"


def test_patch_field_confirms_and_updates_extraction_status(client, admin_headers):
    doc_id = upload_and_wait_document(client, admin_headers)
    r = client.get(f"/api/v1/documents/{doc_id}/extractions", headers=admin_headers)
    fields = [f["field_code"] for f in r.json()["fields"]]

    for code in fields:
        r = client.patch(f"/api/v1/documents/{doc_id}/extractions/fields/{code}", headers=admin_headers, json={"is_confirmed": True})
        assert r.status_code == 200
        assert r.json()["is_confirmed"] is True

    r = client.get(f"/api/v1/documents/{doc_id}/extractions", headers=admin_headers)
    assert r.json()["status"] == "CONFIRMED"


def test_patch_field_manual_value_sets_mapping_method(client, admin_headers):
    doc_id = upload_and_wait_document(client, admin_headers)
    r = client.patch(
        f"/api/v1/documents/{doc_id}/extractions/fields/performance_due_date",
        headers=admin_headers,
        json={"raw_value": "manually corrected", "normalized_value": {"date": "2026-01-01"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["raw_value"] == "manually corrected"
    assert body["confidence"] == 1.0
