import uuid


def test_list_regulations_route_exists(client):
    response = client.get("/api/v1/regulations")

    assert response.status_code == 501


def test_upload_regulation_route_exists(client):
    response = client.post(
        "/api/v1/regulations",
        files={"file": ("manual.pdf", b"%PDF-1.4", "application/pdf")},
        data={"title": "계약사무규정", "doc_type": "규정"},
    )

    assert response.status_code == 501


def test_get_regulation_pdf_route_exists(client):
    response = client.get(f"/api/v1/regulations/{uuid.uuid4()}/pdf")

    assert response.status_code == 501


def test_get_regulation_node_route_exists(client):
    response = client.get(f"/api/v1/regulations/{uuid.uuid4()}/nodes/{uuid.uuid4()}")

    assert response.status_code == 501


def test_get_regulation_route_exists(client):
    response = client.get(f"/api/v1/regulations/{uuid.uuid4()}")

    assert response.status_code == 501


def test_reindex_regulation_route_exists(client):
    response = client.post(f"/api/v1/regulations/{uuid.uuid4()}/reindex", json={})

    assert response.status_code == 501


def test_delete_regulation_route_exists(client):
    response = client.delete(f"/api/v1/regulations/{uuid.uuid4()}")

    assert response.status_code == 501
