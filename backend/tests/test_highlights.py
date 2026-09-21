import uuid


def test_create_highlight_route_exists(client):
    response = client.post(
        f"/api/v1/documents/{uuid.uuid4()}/highlights",
        json={"field_code": "contract_amount", "page_no": 1, "bbox": [0.1, 0.2, 0.3, 0.4]},
    )

    assert response.status_code == 501


def test_patch_highlight_route_exists(client):
    response = client.patch(
        f"/api/v1/highlights/{uuid.uuid4()}",
        json={"bbox": [0.1, 0.2, 0.3, 0.4], "page_no": 1},
    )

    assert response.status_code == 501


def test_delete_highlight_route_exists(client):
    response = client.delete(f"/api/v1/highlights/{uuid.uuid4()}")

    assert response.status_code == 501


def test_create_highlight_requires_bbox_of_four(client):
    response = client.post(
        f"/api/v1/documents/{uuid.uuid4()}/highlights",
        json={"field_code": "contract_amount", "page_no": 1, "bbox": [0.1, 0.2]},
    )

    assert response.status_code == 422
