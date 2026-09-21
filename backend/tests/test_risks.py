import uuid


def test_get_risks_route_exists(client):
    response = client.get(f"/api/v1/documents/{uuid.uuid4()}/risks")

    assert response.status_code == 501


def test_rerun_risks_route_exists(client):
    response = client.post(f"/api/v1/documents/{uuid.uuid4()}/risks/rerun")

    assert response.status_code == 501


def test_patch_risk_route_exists(client):
    response = client.patch(f"/api/v1/risks/{uuid.uuid4()}", json={"status": "ACKNOWLEDGED"})

    assert response.status_code == 501
