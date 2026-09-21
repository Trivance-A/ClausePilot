import uuid


def test_auto_fill_route_exists(client):
    response = client.post(
        "/guarantee-applications/auto-fill",
        json={"document_id": str(uuid.uuid4())},
    )

    assert response.status_code == 501


def test_auto_fill_rejects_missing_document_id(client):
    response = client.post("/guarantee-applications/auto-fill", json={})

    assert response.status_code == 422
