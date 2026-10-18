import uuid

from tests.helpers import upload_and_wait_document


def test_create_patch_delete_highlight(client, admin_headers):
    doc_id = upload_and_wait_document(client, admin_headers)

    r = client.post(
        f"/api/v1/documents/{doc_id}/highlights",
        headers=admin_headers,
        json={"field_code": "contract_name", "page_no": 1, "bbox": [0.1, 0.1, 0.5, 0.15]},
    )
    assert r.status_code == 201
    highlight = r.json()
    assert highlight["origin"] == "manual"
    hid = highlight["id"]

    r = client.patch(f"/api/v1/highlights/{hid}", headers=admin_headers, json={"bbox": [0.1, 0.1, 0.6, 0.2]})
    assert r.status_code == 200
    assert r.json()["bbox"] == [0.1, 0.1, 0.6, 0.2]

    r = client.delete(f"/api/v1/highlights/{hid}", headers=admin_headers)
    assert r.status_code == 204


def test_create_highlight_requires_exactly_one_parent(client, admin_headers):
    doc_id = upload_and_wait_document(client, admin_headers)
    r = client.post(f"/api/v1/documents/{doc_id}/highlights", headers=admin_headers, json={"page_no": 1, "bbox": [0.1, 0.1, 0.2, 0.2]})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_highlight_for_unknown_field_is_404(client, admin_headers):
    r = client.post(
        f"/api/v1/documents/{uuid.uuid4()}/highlights",
        headers=admin_headers,
        json={"field_code": "contract_name", "page_no": 1, "bbox": [0.1, 0.1, 0.2, 0.2]},
    )
    assert r.status_code == 404
