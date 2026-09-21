import uuid


def test_upload_regulation_route_exists(client):
    response = client.post("/regulations", files={"file": ("manual.pdf", b"%PDF-1.4", "application/pdf")})

    assert response.status_code == 501


def test_get_regulation_status_route_exists(client):
    response = client.get(f"/regulations/{uuid.uuid4()}/status")

    assert response.status_code == 501
