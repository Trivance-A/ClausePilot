import uuid


def test_create_guarantee_application_route_exists(client):
    response = client.post(
        "/api/v1/guarantee-applications",
        json={"document_id": str(uuid.uuid4()), "guarantee_type": "contract"},
    )

    assert response.status_code == 501


def test_get_guarantee_application_route_exists(client):
    response = client.get(f"/api/v1/guarantee-applications/{uuid.uuid4()}")

    assert response.status_code == 501


def test_patch_guarantee_application_route_exists(client):
    response = client.patch(
        f"/api/v1/guarantee-applications/{uuid.uuid4()}",
        json={
            "form_values": {
                "contract_name": None,
                "contract_amount": None,
                "guarantee_amount": None,
                "contract_date": None,
                "performance_due_date": None,
                "guarantee_period": None,
                "creditor_name": None,
                "creditor_biz_no": None,
            },
            "status": "SUBMITTED",
        },
    )

    assert response.status_code == 501


def test_create_guarantee_application_rejects_invalid_type(client):
    response = client.post(
        "/api/v1/guarantee-applications",
        json={"document_id": str(uuid.uuid4()), "guarantee_type": "not_a_real_type"},
    )

    assert response.status_code == 422
