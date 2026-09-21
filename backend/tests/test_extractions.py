import uuid


def test_get_extractions_route_exists(client):
    response = client.get(f"/api/v1/documents/{uuid.uuid4()}/extractions")

    assert response.status_code == 501


def test_patch_extraction_field_route_exists(client):
    response = client.patch(
        f"/api/v1/documents/{uuid.uuid4()}/extractions/fields/contract_amount",
        json={"is_confirmed": True},
    )

    assert response.status_code == 501


def test_patch_extraction_field_rejects_invalid_field_code(client):
    response = client.patch(
        f"/api/v1/documents/{uuid.uuid4()}/extractions/fields/not_a_real_field",
        json={"is_confirmed": True},
    )

    assert response.status_code == 422
